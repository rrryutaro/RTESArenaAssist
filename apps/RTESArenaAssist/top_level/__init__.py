"""トップレベル状態 (pregame / chargen / normal-play) ごとの判定と描画を所有するパッケージ。

各 *_state.py は SessionContext を構築し、自状態の描画と (normal-play は)
session_manager 呼び出しを行う。controllers/poll_controller.py は本パッケージ
への dispatcher 化を目指す。
"""
