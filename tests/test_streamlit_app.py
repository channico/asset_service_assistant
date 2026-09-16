import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from assistant_agent import AssistantResult
from service_answer import failure_answer, render_service_answer


class StreamlitAppSmokeTests(unittest.TestCase):
    @staticmethod
    def _app() -> AppTest:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        return AppTest.from_file(app_path)

    def test_initial_page_has_notices_demo_questions_and_chat_input(self) -> None:
        app = self._app().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual([title.value for title in app.title], ["Asset Service Assistant"])
        self.assertEqual(len(app.info), 2)
        self.assertIn("Synthetic data only", app.info[0].value)
        self.assertIn("Read-only assistant", app.info[1].value)
        self.assertEqual([button.label for button in app.button], ["Run demo"] * 3)
        self.assertEqual(len(app.chat_input), 1)

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
            app.button[0].click().run()

        self.assertEqual(list(app.exception), [])
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            "Show asset VEH-1001 and its recorded maintenance history.",
        )


if __name__ == "__main__":
    unittest.main()
