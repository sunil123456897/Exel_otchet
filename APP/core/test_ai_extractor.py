import unittest
from unittest.mock import patch, MagicMock
from core.ai_extractor import LFMExtractor

class TestLFMExtractor(unittest.TestCase):
    @patch('core.ai_extractor.LFMExtractor._load_model')
    def test_extract_fields_returns_dict(self, mock_load):
        # Setup
        extractor = LFMExtractor()
        extractor._is_loaded = True # Mocking that model is loaded

        # Mocking tokenizer and model behavior
        extractor._tokenizer = MagicMock()
        extractor._model = MagicMock()

        # Mocking apply_chat_template
        extractor._tokenizer.apply_chat_template.return_value = "mock_template_output"

        # Mocking tokenizer call
        mock_inputs = {"input_ids": MagicMock()}
        mock_inputs["input_ids"].shape = (1, 10)
        extractor._tokenizer.return_value.to.return_value = mock_inputs

        # Mocking model generation
        mock_outputs = [[0] * 20] # 10 inputs + 10 generated tokens
        extractor._model.generate.return_value = mock_outputs

        # Mocking decode
        extractor._tokenizer.decode.return_value = '{"column_name": "Test Col", "column_type": "string"}'

        # Execution
        result = extractor.extract_fields(
            raw_text="Test Data 1 | Test Data 2",
            schema={"column_name": "str", "column_type": "str"}
        )

        # Assertion
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("column_name"), "Test Col")
        self.assertEqual(result.get("column_type"), "string")

if __name__ == '__main__':
    unittest.main()
