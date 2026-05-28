import unittest
from lecturebot.rag import chunk_text

class TestSemanticChunking(unittest.TestCase):
    def test_basic_sentence_chunking(self):
        text = "This is the first sentence. Here is another one. And a third sentence here."
        chunks = chunk_text(text, chunk_size=10, overlap=2)
        # Sentence boundaries should be preserved
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertTrue(len(chunk.strip()) > 0)

    def test_long_sentence_fallback(self):
        # A single sentence longer than chunk_size
        text = "This is a very long sentence that has more words than the chunk size limit we set for this test case."
        chunks = chunk_text(text, chunk_size=5, overlap=1)
        self.assertGreater(len(chunks), 1)

    def test_empty_text(self):
        self.assertEqual(chunk_text(""), [])

if __name__ == "__main__":
    unittest.main()
