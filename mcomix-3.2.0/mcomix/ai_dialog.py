"""Dialogs and controller for AI-assisted image actions."""

import io
import os
import threading

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from mcomix import ai_client, image_tools, message_dialog, preferences_dialog
from mcomix.i18n import _
from mcomix.preferences import credentials, prefs


class PromptDialog(Gtk.Dialog):
    def __init__(self, window, title, description):
        super().__init__(title, window,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             _('_Send'), Gtk.ResponseType.OK))
        self.set_default_size(560, 300)
        self.set_default_response(Gtk.ResponseType.OK)
        content = self.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)
        label = Gtk.Label(label=description)
        label.set_alignment(0, 0.5)
        label.set_line_wrap(True)
        content.pack_start(label, False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.connect('key-press-event', self._key_press_event)
        scrolled.add(self.text_view)
        content.pack_start(scrolled, True, True, 0)
        self.show_all()
        self.text_view.grab_focus()

    def _key_press_event(self, _widget, event):
        enter_keys = (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter)
        if (event.state & Gdk.ModifierType.CONTROL_MASK and
                event.keyval in enter_keys):
            self.response(Gtk.ResponseType.OK)
            return True
        return False

    def get_prompt(self):
        text_buffer = self.text_view.get_buffer()
        return text_buffer.get_text(
            text_buffer.get_start_iter(), text_buffer.get_end_iter(), True).strip()


class ProgressDialog(Gtk.Dialog):
    def __init__(self, window, title, cancel_callback):
        super().__init__(title, window, Gtk.DialogFlags.DESTROY_WITH_PARENT,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self.set_modal(False)
        self.set_deletable(True)
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
        box.set_border_width(16)
        spinner = Gtk.Spinner()
        spinner.start()
        box.pack_start(spinner, False, False, 0)
        box.pack_start(Gtk.Label(label=_('Waiting for the API response…')),
                       False, False, 0)
        self.get_content_area().pack_start(box, True, True, 0)
        self.connect('response', lambda *_: cancel_callback())
        self.show_all()


class AIHandler:
    def __init__(self, window):
        self._window = window
        self._job_id = 0
        self._busy = False
        self._progress = None

    def ask_about_image(self, *args):
        self._start('text')

    def transform_image(self, *args):
        self._start('image')

    def reset_transformation(self, *args):
        if self._window.imagehandler.clear_page_override():
            self._window.thumbnailsidebar.load_thumbnails()
            self._window.draw_image()
        else:
            self._show_info(_('No AI transformation'),
                _('The current page has no AI-generated image to reset.'))

    def _configuration(self, mode):
        prefix = 'ai text' if mode == 'text' else 'ai image'
        environment_key = ('MCOMIX_AI_TEXT_API_KEY' if mode == 'text'
                           else 'MCOMIX_AI_IMAGE_API_KEY')
        return {
            'endpoint': prefs[prefix + ' endpoint'].strip(),
            'api_key': os.environ.get(environment_key,
                credentials[prefix + ' api key']).strip(),
            'model': prefs[prefix + ' model'].strip(),
            'timeout': prefs[prefix + ' timeout'],
        }

    def _start(self, mode):
        if self._busy or not self._window.imagehandler.page_is_available():
            return
        config = self._configuration(mode)
        if not config['endpoint'] or not config['model']:
            self._show_configuration_error()
            return

        if mode == 'text':
            title = _('Ask AI about image')
            description = _('Enter a question about the current image:')
        else:
            title = _('Transform image with AI')
            description = _('Describe how the current image should be transformed:')
        dialog = PromptDialog(self._window, title, description)
        response = dialog.run()
        prompt = dialog.get_prompt()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if not prompt:
            self._show_info(_('Prompt required'), _('Please enter a prompt.'))
            return

        page = self._window.imagehandler.get_current_page()
        page_path = self._window.imagehandler.get_path_to_page(page)
        generation = self._window.imagehandler.get_generation()
        pixbuf = self._window.imagehandler.get_pixbufs(1)[0]
        if image_tools.is_animation(pixbuf):
            pixbuf = image_tools.static_image(pixbuf)
        output = io.BytesIO()
        image_tools.pixbuf_to_pil(pixbuf).save(output, 'PNG')
        image_png = output.getvalue()

        self._job_id += 1
        job_id = self._job_id
        self._busy = True
        self._set_action_sensitivity(False)
        self._progress = ProgressDialog(self._window, title,
            lambda: self._cancel(job_id))
        thread = threading.Thread(target=self._request,
            args=(job_id, mode, config, prompt, image_png, page, page_path,
                  generation),
            name='mcomix-ai')
        thread.daemon = True
        thread.start()

    def _request(self, job_id, mode, config, prompt, image_png, page, page_path,
                 generation):
        try:
            if mode == 'text':
                result = ai_client.ask_about_image(
                    config['endpoint'], config['api_key'], config['model'],
                    prompt, image_png, config['timeout'])
            else:
                result = ai_client.transform_image(
                    config['endpoint'], config['api_key'], config['model'],
                    prompt, image_png, config['timeout'])
            error = None
        except Exception as caught:
            result = None
            error = caught
        GLib.idle_add(self._finished, job_id, mode, result, error,
                      page, page_path, generation)

    def _finished(self, job_id, mode, result, error, page, page_path,
                  generation):
        if job_id != self._job_id:
            return False
        if self._progress is not None:
            self._progress.destroy()
            self._progress = None
        self._busy = False
        self._set_action_sensitivity(True)
        if error is not None:
            self._show_error(str(error))
        elif mode == 'text':
            self._show_text_result(result)
        else:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(result)
                loader.close()
                pixbuf = loader.get_pixbuf()
                if pixbuf is None:
                    raise ValueError(_('The API returned invalid image data.'))
                applied = self._window.imagehandler.set_page_override(
                    page, pixbuf, expected_path=page_path,
                    expected_generation=generation)
                if not applied:
                    self._show_info(_('Image is no longer open'),
                        _('The result was discarded because its source image is no longer open.'))
                else:
                    self._window.draw_image()
            except Exception as caught:
                self._show_error(str(caught))
        return False

    def _cancel(self, job_id):
        if job_id != self._job_id:
            return
        self._job_id += 1
        if self._progress is not None:
            self._progress.destroy()
            self._progress = None
        self._busy = False
        self._set_action_sensitivity(True)

    def _set_action_sensitivity(self, sensitive):
        if sensitive:
            self._window.uimanager.set_sensitivities()
        else:
            for name in ('ai_ask_image', 'ai_transform_image'):
                self._window.actiongroup.get_action(name).set_sensitive(False)

    def _show_configuration_error(self):
        dialog = message_dialog.MessageDialog(self._window,
            Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.NONE)
        dialog.set_text(_('AI service is not configured'),
            _('Set an endpoint URL and model in Preferences → AI/API.'))
        dialog.add_button(_('Open Preferences'), Gtk.ResponseType.OK)
        dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        if dialog.run() == Gtk.ResponseType.OK:
            preferences_dialog.open_dialog(None, self._window)

    def _show_error(self, detail):
        dialog = message_dialog.MessageDialog(self._window,
            Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE)
        dialog.set_text(_('AI request failed'), detail)
        dialog.run()

    def _show_info(self, title, detail):
        dialog = message_dialog.MessageDialog(self._window,
            Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE)
        dialog.set_text(title, detail)
        dialog.run()

    def _show_text_result(self, result):
        dialog = Gtk.Dialog(_('AI answer'), self._window,
            Gtk.DialogFlags.DESTROY_WITH_PARENT,
            (_('_Copy'), Gtk.ResponseType.APPLY,
             Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        dialog.set_default_size(650, 500)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_border_width(10)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(True)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.get_buffer().set_text(result)
        scrolled.add(text_view)
        dialog.get_content_area().pack_start(scrolled, True, True, 0)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.APPLY:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(result, -1)
        dialog.destroy()
