"""
Module: ai_extractor
Description: Optional AI fallback for column mapping using LFM2.5-350M.
"""

import logging
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LFMExtractor:
    """
    Класс для извлечения полей (AI fallback) с использованием LiquidAI/LFM2.5-350M.
    Загружает модель лениво (lazy-load) для экономии памяти.
    """
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._is_loaded = False
        self._load_error = False

    def _load_model(self) -> None:
        """Внутренний метод для ленивой загрузки модели."""
        if self._is_loaded or self._load_error:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_id = "LiquidAI/LFM2.5-350M"

            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                device_map="auto",
                torch_dtype=torch.bfloat16
            )
            self._is_loaded = True
        except ImportError:
            logger.warning("transformers or torch not installed. AI fallback unavailable.")
            self._load_error = True
        except Exception as e:
            logger.warning(f"Failed to load AI model: {e}")
            self._load_error = True

    def is_available(self) -> bool:
        """Returns True only if transformers and torch are importable AND model can be loaded."""
        self._load_model()
        return self._is_loaded

    def extract_fields(self, raw_text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds a system prompt instructing the model to return strict JSON only.
        Uses tokenizer.apply_chat_template() with add_generation_prompt=True.
        Catches JSON parse errors gracefully and returns empty dict {} on failure.
        """
        if not self.is_available():
            return {}

        system_prompt = (
            "You are an expert data extraction assistant. "
            "Extract the requested fields from the given text based on the provided schema. "
            "Return STRICTLY valid JSON only, with no markdown formatting, no explanations, and no additional text."
        )

        user_prompt = f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\nText:\n{raw_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)

            outputs = self._model.generate(
                **inputs,
                max_new_tokens=300,
                temperature=0.1,
                top_k=50,
                repetition_penalty=1.05
            )

            input_length = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_length:]
            output_text = self._tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

            # Очистка от markdown, если модель его всё же вернула
            if output_text.startswith("```json"):
                output_text = output_text[7:]
            if output_text.startswith("```"):
                output_text = output_text[3:]
            if output_text.endswith("```"):
                output_text = output_text[:-3]

            return json.loads(output_text.strip())

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from AI output: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Error during AI extraction: {e}")
            return {}
