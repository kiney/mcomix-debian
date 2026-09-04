import os
import stat
import tempfile
import unittest

from mcomix import constants, preferences


class AIPreferencesPersistenceTest(unittest.TestCase):
    def test_ai_settings_survive_write_and_reload(self):
        pref_keys = ("ai text endpoint", "ai text model",
                     "ai image endpoint", "ai image model")
        credential_keys = ("ai text api key", "ai image api key")
        original_prefs = {key: preferences.prefs[key] for key in pref_keys}
        original_credentials = {
            key: preferences.credentials[key] for key in credential_keys
        }
        original_paths = (constants.PREFERENCE_PATH,
                          constants.AI_CREDENTIAL_PATH)

        try:
            with tempfile.TemporaryDirectory() as directory:
                constants.PREFERENCE_PATH = os.path.join(directory, "preferences.conf")
                constants.AI_CREDENTIAL_PATH = os.path.join(
                    directory, "ai-credentials.conf")
                expected_prefs = {
                    "ai text endpoint": "https://text.example.test/v1",
                    "ai text model": "vision-test",
                    "ai image endpoint": "https://image.example.test/v1",
                    "ai image model": "image-test",
                }
                expected_credentials = {
                    "ai text api key": "text-test-key",
                    "ai image api key": "image-test-key",
                }
                preferences.prefs.update(expected_prefs)
                preferences.credentials.update(expected_credentials)
                preferences.write_preferences_file()

                preferences.prefs.update({key: "" for key in pref_keys})
                preferences.credentials.update({key: "" for key in credential_keys})
                preferences.read_preferences_file()

                for key, value in expected_prefs.items():
                    self.assertEqual(preferences.prefs[key], value)
                for key, value in expected_credentials.items():
                    self.assertEqual(preferences.credentials[key], value)
                mode = stat.S_IMODE(os.stat(constants.AI_CREDENTIAL_PATH).st_mode)
                self.assertEqual(mode, 0o600)
        finally:
            constants.PREFERENCE_PATH, constants.AI_CREDENTIAL_PATH = original_paths
            preferences.prefs.update(original_prefs)
            preferences.credentials.update(original_credentials)


if __name__ == "__main__":
    unittest.main()
