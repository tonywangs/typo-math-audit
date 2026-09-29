import os
import time
from .common import digest, canonical
from .dataset import SYSTEM
from .scoring import score

SETTINGS = dict(device="cpu", dtype="float32", threads=1, interop_threads=1,
                seed=1907, max_new_tokens=24, do_sample=False, num_beams=1,
                use_cache=True, attention="eager", batch_size=1,
                deterministic_algorithms=True, mkldnn=False)


class Engine:
    def __init__(self, model_dir):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig
        self.torch = torch
        torch.set_num_threads(SETTINGS["threads"])
        torch.set_num_interop_threads(SETTINGS["interop_threads"])
        torch.manual_seed(SETTINGS["seed"])
        torch.use_deterministic_algorithms(True)
        torch.backends.mkldnn.enabled = False
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False,
            torch_dtype=torch.float32, attn_implementation="eager").to("cpu").eval()
        self.generation = GenerationConfig(
            max_new_tokens=SETTINGS["max_new_tokens"], do_sample=False, num_beams=1,
            use_cache=True, eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.eos_token_id, bos_token_id=self.tokenizer.bos_token_id)

    def run(self, case, stop):
        from transformers import StoppingCriteria, StoppingCriteriaList

        class Cancel(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return stop()

        start = time.perf_counter()
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": case["prompt"]}],
            tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(rendered, add_special_tokens=False, return_tensors="pt")
        with self.torch.inference_mode():
            outputs = self.model.generate(**inputs, generation_config=self.generation,
                                          stopping_criteria=StoppingCriteriaList([Cancel()]))
        tokens = outputs[0, inputs["input_ids"].shape[1]:].tolist()
        if stop():
            # Incomplete generations are discarded and retried on resume, never scored.
            raise InterruptedError("Generation cancelled")
        eos = bool(tokens and tokens[-1] == self.tokenizer.eos_token_id)
        truncated = len(tokens) >= SETTINGS["max_new_tokens"] and not eos
        raw = self.tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        text = self.tokenizer.decode(tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        ids = inputs["input_ids"][0].tolist()
        return dict(rendered_prompt=rendered, rendered_prompt_sha256=digest(rendered),
                    input_token_ids=ids, input_token_sha256=digest(canonical(ids)),
                    input_tokens=len(ids), output_token_ids=tokens, output_tokens=len(tokens),
                    raw_completion=raw, completion=text, ended_with_eos=eos, truncated=truncated,
                    elapsed_seconds=time.perf_counter()-start, **score(text, case["answer"], truncated))
