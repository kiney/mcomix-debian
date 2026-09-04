"""Small source-based catalog for Debian-local MComix additions."""

import gettext


GERMAN = {
    'AI/API': 'KI/API',
    'Ask questions about images': 'Fragen zu Bildern stellen',
    'Transform images': 'Bilder transformieren',
    'Endpoint URL:': 'Endpunkt-URL:',
    'API key:': 'API-Schlüssel:',
    'Model:': 'Modell:',
    'Timeout (seconds):': 'Zeitlimit (Sekunden):',
    'Images and prompts are sent to the configured external services.':
        'Bilder und Prompts werden an die konfigurierten externen Dienste gesendet.',
    '_Ask AI about image...': 'KI zum Bild _fragen …',
    'Ask a question about the current image.':
        'Eine Frage zum aktuellen Bild stellen.',
    '_Transform image with AI...': 'Bild mit KI _transformieren …',
    'Transform the current image using an AI service.':
        'Das aktuelle Bild mit einem KI-Dienst transformieren.',
    '_Reset AI transformation': 'KI-Transformation _zurücksetzen',
    'Restore the original image for the current page.':
        'Das Originalbild der aktuellen Seite wiederherstellen.',
    '_Send': '_Senden',
    'Waiting for the API response…': 'Auf die API-Antwort wird gewartet …',
    'No AI transformation': 'Keine KI-Transformation',
    'The current page has no AI-generated image to reset.':
        'Die aktuelle Seite besitzt kein KI-generiertes Bild zum Zurücksetzen.',
    'Ask AI about image': 'KI zum Bild fragen',
    'Enter a question about the current image:':
        'Eine Frage zum aktuellen Bild eingeben:',
    'Transform image with AI': 'Bild mit KI transformieren',
    'Describe how the current image should be transformed:':
        'Beschreiben, wie das aktuelle Bild transformiert werden soll:',
    'Prompt required': 'Prompt erforderlich',
    'Please enter a prompt.': 'Bitte einen Prompt eingeben.',
    'The API returned invalid image data.':
        'Die API hat ungültige Bilddaten zurückgegeben.',
    'Image is no longer open': 'Bild ist nicht mehr geöffnet',
    'The result was discarded because its source image is no longer open.':
        'Das Ergebnis wurde verworfen, weil sein Quellbild nicht mehr geöffnet ist.',
    'AI service is not configured': 'KI-Dienst ist nicht konfiguriert',
    'Set an endpoint URL and model in Preferences → AI/API.':
        'Endpunkt-URL und Modell unter Einstellungen → KI/API festlegen.',
    'Open Preferences': 'Einstellungen öffnen',
    'AI request failed': 'KI-Anfrage fehlgeschlagen',
    'AI answer': 'KI-Antwort',
    '_Copy': '_Kopieren',
    'The API response is too large.': 'Die API-Antwort ist zu groß.',
    'The API returned invalid JSON.': 'Die API hat ungültiges JSON zurückgegeben.',
    'The API returned an unexpected response.':
        'Die API hat eine unerwartete Antwort zurückgegeben.',
    'The API request timed out.': 'Die Zeit für die API-Anfrage wurde überschritten.',
    'The API request failed: %s': 'Die API-Anfrage ist fehlgeschlagen: %s',
    'The API response does not contain a text answer.':
        'Die API-Antwort enthält keine Textantwort.',
    'The API returned an unsupported image URL.':
        'Die API hat eine nicht unterstützte Bild-URL zurückgegeben.',
    'The returned image is too large.': 'Das zurückgegebene Bild ist zu groß.',
    'The returned image is empty or too large.':
        'Das zurückgegebene Bild ist leer oder zu groß.',
    'The API returned an invalid image.':
        'Die API hat ein ungültiges Bild zurückgegeben.',
    'The API response does not contain an image.':
        'Die API-Antwort enthält kein Bild.',
    'The API returned invalid base64 image data.':
        'Die API hat ungültige Base64-Bilddaten zurückgegeben.',
}


class DictionaryTranslations(gettext.NullTranslations):
    def __init__(self, catalog):
        super().__init__()
        self._catalog = catalog

    def gettext(self, message):
        if message in self._catalog:
            return self._catalog[message]
        if self._fallback:
            return self._fallback.gettext(message)
        return message


def get_translation(language):
    if language and language.split('_', 1)[0].split('-', 1)[0] == 'de':
        return DictionaryTranslations(GERMAN)
    return None
