import torch
from peft import PeftModel
import transformers
import gradio as gr
import openbayes_serving as serv

assert (
        "LlamaTokenizer" in transformers._import_structure["models.llama"]
), "LLaMA is now in HuggingFace's main branch.\nPlease reinstall it: pip uninstall transformers && pip install git+https://github.com/huggingface/transformers.git"
from transformers import LlamaTokenizer, LlamaForCausalLM, GenerationConfig


class Predictor:
    tokenizer = None
    model = None
    device = None

    def __init__(self):
        tokenizer = LlamaTokenizer.from_pretrained("decapoda-research/llama-7b-hf")

        BASE_MODEL = "decapoda-research/llama-7b-hf"
        LORA_WEIGHTS = "phodal/unit-userstory"

        if torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

        try:
            if torch.backends.mps.is_available():
                device = "mps"
        except:
            pass

        if device == "cuda":
            model = LlamaForCausalLM.from_pretrained(
                BASE_MODEL,
                load_in_8bit=False,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            model = PeftModel.from_pretrained(
                model, LORA_WEIGHTS, torch_dtype=torch.float16, force_download=True
            )
        elif device == "mps":
            model = LlamaForCausalLM.from_pretrained(
                BASE_MODEL,
                device_map={"": device},
                torch_dtype=torch.float16,
            )
            model = PeftModel.from_pretrained(
                model,
                LORA_WEIGHTS,
                device_map={"": device},
                torch_dtype=torch.float16,
            )
        else:
            model = LlamaForCausalLM.from_pretrained(
                BASE_MODEL, device_map={"": device}, low_cpu_mem_usage=True
            )
            model = PeftModel.from_pretrained(
                model,
                LORA_WEIGHTS,
                device_map={"": device},
            )

        if device != "cpu":
            model.half()
        model.eval()
        if torch.__version__ >= "2":
            model = torch.compile(model)

    def generate_prompt(self, instruction, input=None):
        if input:
            return f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

    ### Instruction:
    {instruction}

    ### Input:
    {input}

    ### Response:"""
        else:
            return f"""Below is an instruction that describes a task. Write a response that appropriately completes the request.

    ### Instruction:
    {instruction}

    ### Response:"""

    def evaluate(
            self,
            instruction,
            input=None,
            temperature=0.1,
            top_p=0.75,
            top_k=40,
            num_beams=4,
            max_new_tokens=128,
            **kwargs,
    ):
        prompt = self.generate_prompt(instruction, input)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            num_beams=num_beams,
            **kwargs,
        )
        with torch.no_grad():
            generation_output = self.model.generate(
                input_ids=input_ids,
                generation_config=generation_config,
                return_dict_in_generate=True,
                output_scores=True,
                max_new_tokens=max_new_tokens,
            )
        s = generation_output.sequences[0]
        output = self.tokenizer.decode(s)
        return output.split("### Response:")[1].strip()

    def predict(self, json):
        g = gr.Interface(
            fn=self.evaluate,
            inputs=[
                gr.components.Textbox(
                    lines=2, label="Instruction", placeholder="Tell me about alpacas."
                ),
                gr.components.Textbox(lines=2, label="Input", placeholder="none"),
                gr.components.Slider(minimum=0, maximum=1, value=0.1, label="Temperature"),
                gr.components.Slider(minimum=0, maximum=1, value=0.75, label="Top p"),
                gr.components.Slider(minimum=0, maximum=100, step=1, value=40, label="Top k"),
                gr.components.Slider(minimum=1, maximum=4, step=1, value=4, label="Beams"),
                gr.components.Slider(
                    minimum=1, maximum=512, step=1, value=128, label="Max tokens"
                ),
            ],
            outputs=[
                gr.inputs.Textbox(
                    lines=5,
                    label="Output",
                )
            ],
            title="🦙🌲 Alpaca-LoRA",
            description="Alpaca-LoRA is a 7B-parameter LLaMA model finetuned to follow instructions. It is trained on the [Stanford Alpaca](https://github.com/tatsu-lab/stanford_alpaca) dataset and makes use of the Huggingface LLaMA implementation. For more information, please visit [the project's website](https://github.com/tloen/alpaca-lora).",
        )
        g.queue(concurrency_count=1)
        g.launch()


if __name__ == '__main__':
    serv.run(Predictor)
