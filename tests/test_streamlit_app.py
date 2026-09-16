import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from assistant_agent import AssistantResult
from service_answer import failure_answer, render_service_answer
from streamlit_app import DEMO_QUESTIONS


class StreamlitAppSmokeTests(unittest.TestCase):
    @staticmethod
    def _app() -> AppTest:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        return AppTest.from_file(app_path)

    def test_initial_page_has_primary_question_form_notices_and_demos(self) -> None:
        app = self._app().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual([title.value for title in app.title], ["Asset Service Assistant"])
        self.assertEqual(len(app.info), 2)
        self.assertIn("Synthetic data only", app.info[0].value)
        self.assertIn("Read-only assistant", app.info[1].value)
        self.assertEqual(len(app.text_input), 1)
        self.assertEqual(app.text_input[0].label, "Your question")
        self.assertIn(
            f'Example question: "{DEMO_QUESTIONS[0][2]}"',
            [caption.value for caption in app.caption],
        )
        markdown_values = [markdown.value for markdown in app.markdown]
        for _, _, question in DEMO_QUESTIONS:
            self.assertIn(f"**Query:** {question}", markdown_values)
        self.assertEqual(
            [button.label for button in app.button],
            ["Ask the assistant", "Run demo", "Run demo", "Run demo"],
        )
        self.assertEqual(len(app.chat_input), 0)

    def test_typed_question_launches_assistant_workflow(self) -> None:
        answer = failure_answer("Offline test response.")
        result = AssistantResult(
            answer=render_service_answer(answer),
            tool_calls=("get_asset_details",),
            limitations=("Offline test response.",),
            service_answer=answer,
        )

        with patch("assistant_agent.run_assistant", return_value=result) as run:
            app = self._app().run()
            app.text_input[0].input("  Show asset VEH-1001.  ")
            app.button[0].click().run()

        self.assertEqual(list(app.exception), [])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], "Show asset VEH-1001.")

    def test_empty_typed_question_is_not_submitted(self) -> None:
        with patch("assistant_agent.run_assistant") as run:
            app = self._app().run()
            app.text_input[0].input("   ")
            app.button[0].click().run()

        self.assertEqual(list(app.exception), [])
        run.assert_not_called()
        self.assertIn("Enter a question", app.warning[0].value)

    def test_demo_button_launches_question_through_assistant_workflow(self) -> None:
        answer = failure_answer("Offline test response.")
        result = AssistantResult(
            answer=render_service_answer(answer),
            tool_calls=("get_asset_details",),
            limitations=("Offline test response.",),
            service_answer=answer,
        )

        with patch("assistant_agent.run_assistant", return_value=result) as run:
            app = self._app().run()
            app.button[1].click().run()

        self.assertEqual(list(app.exception), [])
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            "Show asset VEH-1001 and its recorded maintenance history.",
        )


if __name__ == "__main__":
    unittest.main()
