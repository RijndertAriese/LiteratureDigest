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
            _response('{"relevant": [{"id": 1, "reason": "Shows X."}, "3", 99]}'),
            _response('{"relevant": [2]}'),
        ]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
                mock.patch.object(screen, "Groq", return_value=client):
            kept, rejected, complete = screen.screen_papers("topic", self.papers)

        self.assertEqual([p["title"] for p in kept], ["P1", "P3", "P14"])
        self.assertEqual(kept[0]["reason"], "Shows X.")
        self.assertNotIn("reason", kept[1])
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


class SummariseTopicTest(unittest.TestCase):
    papers = [{"title": "P1", "reason": "Shows X."}]

    def test_returns_summary_text(self):
        client = mock.Mock()
        client.chat.completions.create.return_value = _response('{"summary": "Two themes."}')
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
                mock.patch.object(screen, "Groq", return_value=client):
            self.assertEqual(screen.summarise_topic("t", self.papers), "Two themes.")
        prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("P1 — Shows X.", prompt)

    def test_fails_open(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = RuntimeError("down")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
                mock.patch.object(screen, "Groq", return_value=client):
            self.assertIsNone(screen.summarise_topic("t", self.papers))

    def test_skipped_without_papers_or_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(screen.summarise_topic("t", self.papers))
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}):
            self.assertIsNone(screen.summarise_topic("t", []))


if __name__ == "__main__":
    unittest.main()
