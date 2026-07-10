#!/usr/bin/env python3
"""
TUI Dashboard for 9-Minute English Content Pipeline
"""

import os
import sys
import threading
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Static, Input, Select, Label, TextArea, RichLog
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import ContentPipeline
from modules.cache import ContentCache


class PipelineOutput(Static):
    """Displays pipeline progress output in real-time."""
    output: reactive[str] = reactive("")

    def watch_output(self, value: str):
        self.update(value)


class GenerateScreen(Screen):
    """Main generation configuration screen."""
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Vertical(
                Label("[bold]9-Minute English Content Generator[/bold]", id="title"),
                Label("Configure your video generation", id="subtitle"),
                # Topic input
                Label("Topic / Theme"),
                Input(placeholder="e.g. daily English conversations", id="topic", value="pivotal English phrases"),
                # Count input
                Label("Number of Unique Phrases"),
                Input(placeholder="e.g. 30", id="count", value="30", type="integer"),
                # Duration input
                Label("Target Duration (seconds, default 540 = 9 min)"),
                Input(placeholder="540", id="duration", value="540", type="integer"),
                # Output filename
                Label("Output Filename"),
                Input(placeholder="e.g. my_video.mp4", id="output", value=""),
                # Action buttons
                Horizontal(
                    Button("Generate Video", variant="primary", id="generate"),
                    Button("Clear Cache", variant="error", id="clear_cache"),
                    Button("Quit", variant="default", id="quit"),
                    classes="button-row"
                ),
                id="config-panel",
            ),
            ScrollableContainer(
                RichLog(id="log", highlight=True, max_lines=200),
                id="log-panel",
            ),
            id="main-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#log", RichLog)
        
        if event.button.id == "quit":
            self.app.exit()
        
        elif event.button.id == "clear_cache":
            cache = ContentCache()
            for f in os.listdir(cache.audio_dir):
                os.remove(os.path.join(cache.audio_dir, f))
            cache.phrases_cache = {}
            cache.translations_cache = {}
            cache._save_json(cache.phrases_cache, cache.phrases_cache_path)
            cache._save_json(cache.translations_cache, cache.translations_cache_path)
            log.write("[green]✓ Cache cleared successfully[/green]")
        
        elif event.button.id == "generate":
            topic = self.query_one("#topic", Input).value.strip()
            try:
                count = int(self.query_one("#count", Input).value)
            except ValueError:
                log.write("[red]✗ Invalid count value[/red]")
                return
            try:
                duration = int(self.query_one("#duration", Input).value)
            except ValueError:
                duration = 540
            output = self.query_one("#output_filename", Input).value.strip()
            if not output:
                output = None
            
            # Disable button during generation
            btn = event.button
            btn.disabled = True
            btn.label = "Generating..."
            
            def run_pipeline():
                try:
                    # Redirect print to the log widget
                    pipe_log = []
                    original_print = __builtins__["print"]
                    def tui_print(*args, **kwargs):
                        line = " ".join(str(a) for a in args)
                        pipe_log.append(line)
                        self.call_from_thread(log.write, line)
                        original_print(*args, **kwargs)
                    
                    __builtins__["print"] = tui_print
                    try:
                        pipeline = ContentPipeline()
                        pipeline.run(topic=topic, count=count, output_filename=output)
                    finally:
                        __builtins__["print"] = original_print
                        
                    self.call_from_thread(log.write, "[bold green]🎉 Video generated successfully![/bold green]")
                except Exception as e:
                    self.call_from_thread(log.write, f"[red]✗ Error: {e}[/red]")
                finally:
                    self.call_from_thread(btn.update, "Generate Content")
                    self.call_from_thread(btn.__setattr__, "disabled", False)
            
            threading.Thread(target=run_pipeline, daemon=True).start()


class Dashboard(App):
    """Main TUI Dashboard for 9-Minute English Pipeline."""
    
    TITLE = "9-Minute English Content Generator"
    CSS = """
    Screen {
        background: #0A0B10;
    }
    
    #main-container {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        height: 100%;
    }
    
    #config-panel {
        padding: 1;
        border: solid $primary;
        height: 100%;
    }
    
    #title {
        text-style: bold;
        color: $accent;
        text-align: center;
        padding-bottom: 1;
    }
    
    #subtitle {
        color: $secondary;
        text-align: center;
        padding-bottom: 1;
    }
    
    #log-panel {
        border: solid $secondary;
        height: 100%;
        padding: 1;
    }
    
    #log {
        height: 100%;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    .button-row {
        align: center middle;
        margin-top: 1;
        margin-bottom: 1;
    }
    
    Button {
        margin: 0 1;
    }
    
    #generate {
        width: 24;
    }
    
    #clear_cache {
        width: 16;
        background: $error;
        color: $text;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("g", "focus_generate", "Generate"),
        Binding("c", "clear_cache", "Clear Cache"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield GenerateScreen()
        yield Footer()
    
    def on_mount(self) -> None:
        self.title = self.TITLE


if __name__ == "__main__":
    app = Dashboard()
    app.run()