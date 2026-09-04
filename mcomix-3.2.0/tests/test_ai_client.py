import base64
import io
import unittest
from unittest import mock

from PIL import Image
import requests

from mcomix import ai_client


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, "PNG")
    return output.getvalue()


def response(payload, status=200):
    result = mock.Mock()
    result.ok = status < 400
    result.status_code = status
    result.reason = "error"
    result.text = ""
    result.content = b"{}"
    result.json.return_value = payload
    return result


class AskAboutImageTest(unittest.TestCase):
    @mock.patch("mcomix.ai_client.requests.post")
    def test_sends_multimodal_chat_completion(self, post):
        post.return_value = response({
            "choices": [{"message": {"content": "A red square."}}],
        })

        answer = ai_client.ask_about_image(
            "https://example.test/chat", "secret", "vision-model",
            "What is shown?", png_bytes(), 12)

        self.assertEqual(answer, "A red square.")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "vision-model")
        content = kwargs["json"]["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "What is shown?")
        self.assertTrue(content[1]["image_url"]["url"].startswith(
            "data:image/png;base64,"))

    @mock.patch("mcomix.ai_client.requests.post")
    def test_accepts_content_parts(self, post):
        post.return_value = response({"choices": [{"message": {"content": [
            {"type": "text", "text": "First"},
            {"type": "text", "text": "Second"},
        ]}}]})
        answer = ai_client.ask_about_image(
            "https://example.test/chat", "", "model", "prompt", png_bytes(), 12)
        self.assertEqual(answer, "First\nSecond")
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    @mock.patch("mcomix.ai_client.requests.post")
    def test_reports_provider_error(self, post):
        post.return_value = response({"error": {"message": "bad model"}}, 400)
        with self.assertRaisesRegex(ai_client.AIError, "HTTP 400: bad model"):
            ai_client.ask_about_image(
                "https://example.test/chat", "", "model", "prompt", png_bytes(), 12)

    @mock.patch("mcomix.ai_client.requests.post", side_effect=requests.Timeout())
    def test_reports_timeout(self, post):
        with self.assertRaisesRegex(ai_client.AIError, "timed out"):
            ai_client.ask_about_image(
                "https://example.test/chat", "", "model", "prompt", png_bytes(), 12)


class TransformImageTest(unittest.TestCase):
    @mock.patch("mcomix.ai_client.requests.post")
    def test_decodes_base64_image(self, post):
        expected = png_bytes()
        post.return_value = response({
            "data": [{"b64_json": base64.b64encode(expected).decode("ascii")}],
        })
        actual = ai_client.transform_image(
            "https://example.test/edit", "secret", "image-model",
            "make it blue", png_bytes(), 12)
        self.assertEqual(actual, expected)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["data"]["model"], "image-model")
        self.assertEqual(kwargs["files"]["image"][2], "image/png")

    @mock.patch("mcomix.ai_client.requests.get")
    @mock.patch("mcomix.ai_client.requests.post")
    def test_downloads_url_image(self, post, get):
        post.return_value = response({"data": [{"url": "https://cdn.test/result"}]})
        downloaded = response({})
        downloaded.iter_content.return_value = [png_bytes()]
        get.return_value = downloaded
        actual = ai_client.transform_image(
            "https://example.test/edit", "", "model", "prompt", png_bytes(), 12)
        self.assertEqual(actual, png_bytes())

    @mock.patch("mcomix.ai_client.requests.post")
    def test_rejects_invalid_image(self, post):
        post.return_value = response({"data": [{
            "b64_json": base64.b64encode(b"not an image").decode("ascii"),
        }]})
        with self.assertRaisesRegex(ai_client.AIError, "invalid image"):
            ai_client.transform_image(
                "https://example.test/edit", "", "model", "prompt", png_bytes(), 12)


if __name__ == "__main__":
    unittest.main()
