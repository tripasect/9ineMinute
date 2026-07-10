# CLI Usage & Examples

## Interactive Mode

Run with no flags for the full interactive menu:

```bash
python cli.py
```

---

## Non-interactive (One-shot) Mode

Pass any flag to skip all prompts. Unset flags use sensible defaults.

### Presets

```bash
# 9-minute full video
python cli.py -p 9min -y

# 6-minute video
python cli.py -p 6min -y

# 3-minute short (default)
python cli.py -p 3min -y

# 1-minute test
python cli.py -p 1min -y

# 30-second quick test
python cli.py -p 30s -y
```

### Custom Duration

```bash
# 2-minute video (120s)
python cli.py -d 120 -y

# 5-minute video
python cli.py -d 300 -y

# 10-minute video (overrides presets)
python cli.py -d 600 -y
```

### Topics

By name:

```bash
python cli.py -t "business English conversations" -y
python cli.py -t "travel English phrases" -y
python cli.py -t "emotional and romantic phrases" -y
python cli.py -t "everyday English slang" -y
python cli.py -t "English proverbs and idioms" -y
```

By index (1–10):

```bash
python cli.py -t 2 -y     # travel English phrases
python cli.py -t 5 -y     # everyday English slang
python cli.py -t 10 -y    # English proverbs and idioms
```

Custom topic (any string):

```bash
python cli.py -t "medical English for doctors" -y
python cli.py -t "legal terminology for beginners" -y
python cli.py -t "sports commentary phrases" -y
```

### CEFR Levels

```bash
python cli.py -l A1 -y    # beginner
python cli.py -l A2 -y    # elementary
python cli.py -l B1 -y    # intermediate
python cli.py -l B2 -y    # upper-intermediate
python cli.py -l C1 -y    # advanced
python cli.py -l any -y   # any level (default)
```

### English Repeat Mode

Repeats the English phrase after the Persian translation:

```bash
python cli.py -p 9min -r -y
python cli.py -d 180 -t "business English conversations" -l B1 -r -y
```

### Custom Output

```bash
python cli.py -o "my_video.mp4" -y
python cli.py -p 30s -o "quick-test.mp4" -y
```

### Suppress Header (for scripts)

```bash
python cli.py -p 30s -y --plain
```

---

## Combined Examples

```bash
# 9-minute travel English for beginners with repeat mode
python cli.py -p 9min -t "travel English phrases" -l A1 -r -y -o "travel-a1.mp4"

# 3-minute slang video, upper-intermediate level
python cli.py -p 3min -t 5 -l B2 -y

# 2-minute custom topic, no header (cron/script friendly)
python cli.py -d 120 -t "job interview questions" -l B1 -y --plain

# 30-second smoke test with everything explicit
python cli.py -p 30s -t 1 -l any -y -o "smoke-test.mp4" --plain

# 6-minute video, 25 phrases, romantic topic, repeat English
python cli.py -p 6min -c 25 -t "emotional and romantic phrases" -r -y

# Override preset count
python cli.py -p 9min -c 10 -y

# Full custom: 4 minutes, 12 phrases, medical topic, advanced, repeat
python cli.py -d 240 -c 12 -t "medical English" -l C1 -r -y -o "medical-c1.mp4"
```

---

## Common Workflows

### Quick sanity check (30s)

```bash
python cli.py -p 30s -y --plain
```

### Full production video

```bash
python cli.py -p 9min -t "pivotal English phrases" -l any -r -y
```

### Batch script (cron / CI)

```bash
#!/bin/bash
for topic in 1 3 5 7 9; do
  python cli.py -p 3min -t "$topic" -y --plain -o "batch-topic-$topic.mp4"
done
```

### Watch the output folder

```bash
ls -lh output/
```

---

## Config Reference

| Setting             | Config key               | Default               |
|---------------------|--------------------------|-----------------------|
| Presets             | `-p` / `--preset`        | `3min`                |
| Duration (s)        | `-d` / `--duration`      | preset value          |
| Phrase count        | `-c` / `--count`         | preset value          |
| Topic               | `-t` / `--topic`         | `pivotal English phrases` |
| CEFR level          | `-l` / `--level`         | `any`                 |
| Output filename     | `-o` / `--output`        | `video_english_persian.mp4` |
| Repeat English      | `-r` / `--repeat`        | off                   |
| Skip confirm        | `-y` / `--yes`           | prompt                |
| Plain output        | `--plain`                | fancy header          |
