; PAPER_A4_LEFT_MID_RIGHT_CROSS20_GCODE_V39
; firmware=PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27
; paper_map=DISABLED direct_user_coordinates=1
; placement=UPPER_BLANK nominal_paper_row_y=185
; purpose=raw_user_basis_not_paper_XY_or_paper_20mm
; horizontal=LEFT_TO_RIGHT vertical=BOTTOM_TO_TOP
G21
G90
G94
F180
S1000
M5
; LEFT_HORIZONTAL nominal_paper_center=(45.000,185.000) command_user_center=(222.904,-1.657)
G0 X212.904 Y-1.657
M3
G1 X232.904 Y-1.657
M5
; LEFT_VERTICAL nominal_paper_center=(45.000,185.000) command_user_center=(222.904,-1.657)
G0 X222.904 Y-11.657
M3
G1 X222.904 Y8.343
M5
; MIDDLE_HORIZONTAL nominal_paper_center=(105.000,185.000) command_user_center=(262.581,54.963)
G0 X252.581 Y54.963
M3
G1 X272.581 Y54.963
M5
; MIDDLE_VERTICAL nominal_paper_center=(105.000,185.000) command_user_center=(262.581,54.963)
G0 X262.581 Y44.963
M3
G1 X262.581 Y64.963
M5
; RIGHT_HORIZONTAL nominal_paper_center=(165.000,185.000) command_user_center=(298.521,104.539)
G0 X288.521 Y104.539
M3
G1 X308.521 Y104.539
M5
; RIGHT_VERTICAL nominal_paper_center=(165.000,185.000) command_user_center=(298.521,104.539)
G0 X298.521 Y94.539
M3
G1 X298.521 Y114.539
M5
