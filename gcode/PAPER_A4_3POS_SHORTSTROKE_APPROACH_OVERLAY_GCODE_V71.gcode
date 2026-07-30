; PAPER_A4_3POS_SHORTSTROKE_APPROACH_OVERLAY_GCODE_V71
; firmware_required=PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32
; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM
; purpose=SHORT_STROKE_TANGENT_APPROACH_ISOLATION
; line_length_is_fixed_at_4mm_and_is_not_under_test
; each_nominal_line_is_drawn_once_in_each_opposite_direction
; rows_top_to_bottom=A1P2,A3,A5
; columns_left_to_right=L,M,R
G21
G90
G94
F300
S1000
M5
; BEGIN_CELL_A1P2_L
; row=A1P2 group=L approach=1.2mm axis=H direction=LR
G0 X36.800 Y226.000
G0 X38.000 Y226.000
M3
G1 X42.000 Y226.000
M5
; row=A1P2 group=L approach=1.2mm axis=H direction=RL
G0 X43.200 Y226.000
G0 X42.000 Y226.000
M3
G1 X38.000 Y226.000
M5
; row=A1P2 group=L approach=1.2mm axis=V direction=BT
G0 X49.000 Y217.800
G0 X49.000 Y219.000
M3
G1 X49.000 Y223.000
M5
; row=A1P2 group=L approach=1.2mm axis=V direction=TB
G0 X49.000 Y224.200
G0 X49.000 Y223.000
M3
G1 X49.000 Y219.000
M5
; END_CELL_A1P2_L
; BEGIN_CELL_A1P2_M
; row=A1P2 group=M approach=1.2mm axis=H direction=LR
G0 X96.800 Y226.000
G0 X98.000 Y226.000
M3
G1 X102.000 Y226.000
M5
; row=A1P2 group=M approach=1.2mm axis=H direction=RL
G0 X103.200 Y226.000
G0 X102.000 Y226.000
M3
G1 X98.000 Y226.000
M5
; row=A1P2 group=M approach=1.2mm axis=V direction=BT
G0 X109.000 Y217.800
G0 X109.000 Y219.000
M3
G1 X109.000 Y223.000
M5
; row=A1P2 group=M approach=1.2mm axis=V direction=TB
G0 X109.000 Y224.200
G0 X109.000 Y223.000
M3
G1 X109.000 Y219.000
M5
; END_CELL_A1P2_M
; BEGIN_CELL_A1P2_R
; row=A1P2 group=R approach=1.2mm axis=H direction=LR
G0 X156.800 Y226.000
G0 X158.000 Y226.000
M3
G1 X162.000 Y226.000
M5
; row=A1P2 group=R approach=1.2mm axis=H direction=RL
G0 X163.200 Y226.000
G0 X162.000 Y226.000
M3
G1 X158.000 Y226.000
M5
; row=A1P2 group=R approach=1.2mm axis=V direction=BT
G0 X169.000 Y217.800
G0 X169.000 Y219.000
M3
G1 X169.000 Y223.000
M5
; row=A1P2 group=R approach=1.2mm axis=V direction=TB
G0 X169.000 Y224.200
G0 X169.000 Y223.000
M3
G1 X169.000 Y219.000
M5
; END_CELL_A1P2_R
; BEGIN_CELL_A3_L
; row=A3 group=L approach=3.0mm axis=H direction=LR
G0 X35.000 Y210.000
G0 X38.000 Y210.000
M3
G1 X42.000 Y210.000
M5
; row=A3 group=L approach=3.0mm axis=H direction=RL
G0 X45.000 Y210.000
G0 X42.000 Y210.000
M3
G1 X38.000 Y210.000
M5
; row=A3 group=L approach=3.0mm axis=V direction=BT
G0 X49.000 Y200.000
G0 X49.000 Y203.000
M3
G1 X49.000 Y207.000
M5
; row=A3 group=L approach=3.0mm axis=V direction=TB
G0 X49.000 Y210.000
G0 X49.000 Y207.000
M3
G1 X49.000 Y203.000
M5
; END_CELL_A3_L
; BEGIN_CELL_A3_M
; row=A3 group=M approach=3.0mm axis=H direction=LR
G0 X95.000 Y210.000
G0 X98.000 Y210.000
M3
G1 X102.000 Y210.000
M5
; row=A3 group=M approach=3.0mm axis=H direction=RL
G0 X105.000 Y210.000
G0 X102.000 Y210.000
M3
G1 X98.000 Y210.000
M5
; row=A3 group=M approach=3.0mm axis=V direction=BT
G0 X109.000 Y200.000
G0 X109.000 Y203.000
M3
G1 X109.000 Y207.000
M5
; row=A3 group=M approach=3.0mm axis=V direction=TB
G0 X109.000 Y210.000
G0 X109.000 Y207.000
M3
G1 X109.000 Y203.000
M5
; END_CELL_A3_M
; BEGIN_CELL_A3_R
; row=A3 group=R approach=3.0mm axis=H direction=LR
G0 X155.000 Y210.000
G0 X158.000 Y210.000
M3
G1 X162.000 Y210.000
M5
; row=A3 group=R approach=3.0mm axis=H direction=RL
G0 X165.000 Y210.000
G0 X162.000 Y210.000
M3
G1 X158.000 Y210.000
M5
; row=A3 group=R approach=3.0mm axis=V direction=BT
G0 X169.000 Y200.000
G0 X169.000 Y203.000
M3
G1 X169.000 Y207.000
M5
; row=A3 group=R approach=3.0mm axis=V direction=TB
G0 X169.000 Y210.000
G0 X169.000 Y207.000
M3
G1 X169.000 Y203.000
M5
; END_CELL_A3_R
; BEGIN_CELL_A5_L
; row=A5 group=L approach=5.0mm axis=H direction=LR
G0 X33.000 Y194.000
G0 X38.000 Y194.000
M3
G1 X42.000 Y194.000
M5
; row=A5 group=L approach=5.0mm axis=H direction=RL
G0 X47.000 Y194.000
G0 X42.000 Y194.000
M3
G1 X38.000 Y194.000
M5
; row=A5 group=L approach=5.0mm axis=V direction=BT
G0 X49.000 Y182.000
G0 X49.000 Y187.000
M3
G1 X49.000 Y191.000
M5
; row=A5 group=L approach=5.0mm axis=V direction=TB
G0 X49.000 Y196.000
G0 X49.000 Y191.000
M3
G1 X49.000 Y187.000
M5
; END_CELL_A5_L
; BEGIN_CELL_A5_M
; row=A5 group=M approach=5.0mm axis=H direction=LR
G0 X93.000 Y194.000
G0 X98.000 Y194.000
M3
G1 X102.000 Y194.000
M5
; row=A5 group=M approach=5.0mm axis=H direction=RL
G0 X107.000 Y194.000
G0 X102.000 Y194.000
M3
G1 X98.000 Y194.000
M5
; row=A5 group=M approach=5.0mm axis=V direction=BT
G0 X109.000 Y182.000
G0 X109.000 Y187.000
M3
G1 X109.000 Y191.000
M5
; row=A5 group=M approach=5.0mm axis=V direction=TB
G0 X109.000 Y196.000
G0 X109.000 Y191.000
M3
G1 X109.000 Y187.000
M5
; END_CELL_A5_M
; BEGIN_CELL_A5_R
; row=A5 group=R approach=5.0mm axis=H direction=LR
G0 X153.000 Y194.000
G0 X158.000 Y194.000
M3
G1 X162.000 Y194.000
M5
; row=A5 group=R approach=5.0mm axis=H direction=RL
G0 X167.000 Y194.000
G0 X162.000 Y194.000
M3
G1 X158.000 Y194.000
M5
; row=A5 group=R approach=5.0mm axis=V direction=BT
G0 X169.000 Y182.000
G0 X169.000 Y187.000
M3
G1 X169.000 Y191.000
M5
; row=A5 group=R approach=5.0mm axis=V direction=TB
G0 X169.000 Y196.000
G0 X169.000 Y191.000
M3
G1 X169.000 Y187.000
M5
; END_CELL_A5_R
M5
