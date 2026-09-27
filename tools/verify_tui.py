"""Capture real Textual frames from an offline verified edit, at two terminal sizes."""
import argparse
import asyncio
import os
from dataclasses import replace
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("NO_COLOR", None)
os.environ["COLORTERM"] = "truecolor"
from harness.config import Settings
from harness.tui import RakshakTUI
from textual.widgets import TabbedContent


async def capture(output):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for width, height in ((120, 40), (80, 24)):
            settings = replace(Settings.from_env({}), data=Path(tmp) / str(width))
            app = RakshakTUI(workspace=Path(tmp), settings=settings)
            async with app.run_test(size=(width, height)) as pilot:
                await pilot.click("#demo")
                for _ in range(150):
                    await pilot.pause(.1)
                    if app.finished:
                        break
                assert app.finished and app.store.detail(app.selected)["status"] == "verified_candidate"
                app.query_one("#views", TabbedContent).active = "patch-tab"
                await pilot.pause(.5)
                assert app.query_one("#patch").lines, "Patch tab must actually render code"
                app.save_screenshot(filename="tui-" + str(width) + ".svg", path=str(output))
                print("Verified patch, pipeline and error sidebar at", width, height)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/tui")
    asyncio.run(capture(Path(parser.parse_args().output)))
