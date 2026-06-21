"""通常プレイ中の普段時 (active session なし) で発火する独立描画モジュール群。

trigger / newpop_pickup / building_entry / journal / level_up を各 module に
分離し、controllers/poll_controller.py の汎用 block 群を物理切離する。

各モジュールは自身の panel_owner を所有し、変化検出キャッシュを持つことで
5Hz poll 内の負荷を抑制する。
"""
