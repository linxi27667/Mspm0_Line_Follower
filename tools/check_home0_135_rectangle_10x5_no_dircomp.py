"""Offline pulse and limit check for HOME0_135_CENTER_ANCHOR_10X5_AXES_V6."""

import numpy as np

import check_workspace_rectangle_10x5_no_dircomp as test
import check_workspace_square_dircomp as model


model.OFFSET_X_MM = np.float32(-35.901242)
model.OFFSET_Y_MM = np.float32(182.889598)
model.THETA_LIMIT_DEG = np.float32(0.0)
model.PSI_LIMIT_DEG = np.float32(135.0)
model.THETA_MIN_DEG = np.float32(1.0)
model.PSI_MIN_DEG = np.float32(136.0)
model.THETA_REV_PSI_STEPS = 0
model.PSI_REV_PSI_STEPS = 0


if __name__ == "__main__":
    test.main()
