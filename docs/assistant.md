# Assistant

The `ai` plugin adds a card to the home screen where you can ask about your
homelab in plain language: *Is everything OK? What's using the CPU? When was
the last backup of nextcloud? What broke last night?* A model running on your own
hardware through [Ollama](https://ollama.com) answers. Nothing leaves your network.

```toml
[plugins.ai]
url = "http://192.168.1.30:11434"
model = "qwen3:4b-instruct"     # small models work well: the answers come from faro's data
label = "Qwen3 4B · mini PC"    # shown in the card
threads = 8                     # CPU threads for Ollama (optional)
keep_alive = "30m"              # how long the model stays in RAM after a question
log = false                     # true: keep questions and answers in data_dir/ai.jsonl
guide = '''
The NAS keeps everything and is always on. The mini PC runs Jellyfin and this assistant.
Movies are requested in Jellyseerr (https://requests.example.com).
'''
```

`guide` is where you explain whatever faro can't see: what each machine is for,
where things are requested, what to do when something typical happens. The
assistant uses it like a manual.

## How it answers

Each question takes two calls to the model:

1. **Pick a tool.** The prompt holds the rules, the guide, the list of tools and a
   text summary of the live state (hosts, pools, filesystems, SMART, guests,
   containers, backups, services, open problems, latest alerts). The model
   replies with JSON, constrained by a schema to `{"tool": <one of the tools or
   "none">, "argument": "..."}`.
2. **Answer.** faro runs the tool, adds its result to the question and streams
   the model's answer to the browser word by word.

Both calls start with exactly the same system prompt and state, so Ollama reuses
its prompt cache and only has to read the new part. The state is split into what
barely changes (disks, guests, backups) and what changes every second (CPU, RAM),
with the slow part first. On a CPU-only mini PC with a 4B model, the first word
arrives in about 3 s once the model is loaded. Opening the input box starts
loading it in the background.

## Tools

| Tool | What it looks up |
|---|---|
| `cpu` | CPU per guest on each host over the last 15 minutes (sampled every 5 s) |
| `guests` | every VM and container, running or not, cores, RAM and description |
| `disks` | model, size, temperature, hours, wear and SMART of every disk |
| `backups` | the latest vzdump of each guest on each backup storage |
| `alerts` | the latest alerts with their date |

Every tool only reads. Other plugins add their own tools ([plugins.md](plugins.md)).

## Safety rails

- It only talks about the homelab. Anything else gets a fixed polite refusal.
- It may only state facts that are in the data. When the answer isn't there, it
  says it doesn't know.
- One question at a time: a small model on a CPU shouldn't be doing two things at once.
- **Sleep** unloads the model and gives its RAM back. It loads again with the next question.
