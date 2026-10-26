import os
import unittest
from unittest import mock

from bot import screen


def _response(content):
    msg = mock.Mock(content=content)
    return mock.Mock(choices=[mock.Mock(message=msg)])


class ScreenPapersTest(unittest.TestCase):
    def setUp(self):
        self.papers = [{"title": f"P{i}", "abstract": "x"} for i in range(1, 16)]

    def test_keeps_only_relevant_numbers_per_batch(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = [
            _response('{"relevant": [1, "3", 99]}'),
            _response('{"relevant": [2]}'),
        ]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
                mock.patch.object(screen, "Groq", return_value=client):
            kept, rejected, complete = screen.screen_papers("topic", self.papers)

        self.assertEqual([p["title"] for p in kept], ["P1", "P3", "P14"])
        self.assertEqual(rejected, 12)
        self.assertTrue(complete)

    def test_failed_batch_is_kept_unscreened(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = [
            RuntimeError("rate limit"),
            _response('{"relevant": []}'),
        ]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
                mock.patch.object(screen, "Groq", return_value=client):
            kept, rejected, complete = screen.screen_papers("topic", self.papers)

        self.assertEqual(len(kept), 12)
        self.assertEqual(rejected, 3)
        self.assertFalse(complete)

    def test_without_api_key_everything_is_kept(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            kept, rejected, complete = screen.screen_papers("topic", self.papers)
        self.assertEqual(len(kept), 15)
        self.assertEqual(rejected, 0)


if __name__ == "__main__":
    unittest.main()
