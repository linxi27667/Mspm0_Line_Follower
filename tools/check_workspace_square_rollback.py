"""Offline check for WORKSPACE_NO_DIRCOMP_4P5MM_ROLLBACK_V4."""

import check_workspace_square_dircomp as model


model.THETA_REV_PSI_STEPS = 0
model.PSI_REV_PSI_STEPS = 0
model.CW = (
    (3.0, -0.86),
    (7.5, -0.86),
    (7.5, -5.36),
    (3.0, -5.36),
    (3.0, -0.86),
)
model.CCW = (
    (3.0, -0.86),
    (3.0, -5.36),
    (7.5, -5.36),
    (7.5, -0.86),
    (3.0, -0.86),
)


if __name__ == "__main__":
    model.main()
