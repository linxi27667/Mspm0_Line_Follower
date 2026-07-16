import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FAKE_BUS = r'''
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "bsp_icm42688.h"

static uint8_t regs[256];
static bool cs_active;
static bool read_mode;
static uint8_t active_reg;
static uint16_t transfer_index;
static uint16_t cs_low_count;
static uint16_t cs_high_count;
static bool force_transfer_failure;

static void fake_cs_write(bool high)
{
    if (high) {
        cs_active = false;
        cs_high_count++;
    } else {
        cs_active = true;
        transfer_index = 0;
        cs_low_count++;
    }
}

static bool fake_spi_transfer(uint8_t tx, uint8_t *rx)
{
    if (force_transfer_failure || !cs_active || rx == NULL) return false;
    if (transfer_index == 0) {
        read_mode = (tx & 0x80u) != 0u;
        active_reg = tx & 0x7fu;
        *rx = 0;
    } else if (read_mode) {
        *rx = regs[active_reg++];
    } else {
        regs[active_reg++] = tx;
        *rx = 0;
    }
    transfer_index++;
    return true;
}

static void fake_delay(uint32_t ms) { (void)ms; }

static imu_sensor_t make_sensor(void)
{
    imu_sensor_t sensor;
    memset(&sensor, 0, sizeof(sensor));
    sensor.Spi_Transfer = fake_spi_transfer;
    sensor.Cs_Write = fake_cs_write;
    sensor.Delay_ms = fake_delay;
    regs[ICM42688_WHO_AM_I] = ICM42688_WHO_AM_I_VALUE;
    return sensor;
}

static void __attribute__((unused)) set_s16(uint8_t reg, int16_t value)
{
    regs[reg] = (uint8_t)(((uint16_t)value) >> 8);
    regs[(uint8_t)(reg + 1u)] = (uint8_t)value;
}

static int __attribute__((unused)) nearf(float actual, float expected, float tolerance)
{
    return fabsf(actual - expected) <= tolerance;
}
'''


def compile_and_run(body: str) -> subprocess.CompletedProcess:
    source = FAKE_BUS + "\n" + textwrap.dedent(body)
    with tempfile.TemporaryDirectory(prefix="imu_logic_test_") as tmpdir:
        src = Path(tmpdir) / "imu_logic_test.c"
        exe = Path(tmpdir) / "imu_logic_test.exe"
        src.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [
                "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "BSP" / "Inc"),
                str(src), str(ROOT / "BSP" / "Src" / "bsp_icm42688.c"),
                "-lm", "-o", str(exe),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            return compile_result
        return subprocess.run([str(exe)], capture_output=True, text=True)


class ImuLogicTests(unittest.TestCase):
    def test_init_checks_identity_and_programs_expected_range_and_odr(self):
        result = compile_and_run(r'''
            int main(void)
            {
                imu_sensor_t sensor = make_sensor();
                if (!Bsp_Icm42688_Init_Device(&sensor)) return 1;
                if (!sensor.initialized || !sensor.data_valid) return 2;
                if (regs[ICM42688_ACCEL_CONFIG0] != 0x4f) return 3;
                if (regs[ICM42688_GYRO_CONFIG0] != 0x4f) return 4;
                if ((regs[ICM42688_PWR_MGMT0] & 0x0f) != 0x0f) return 5;
                regs[ICM42688_WHO_AM_I] = 0;
                sensor = make_sensor();
                regs[ICM42688_WHO_AM_I] = 0;
                if (Bsp_Icm42688_Init_Device(&sensor)) return 6;
                if (sensor.initialized || sensor.data_valid) return 7;
                return 0;
            }
        ''')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_burst_read_uses_one_cs_window_and_converts_units(self):
        result = compile_and_run(r'''
            int main(void)
            {
                imu_sensor_t sensor = make_sensor();
                if (!Bsp_Icm42688_Init_Device(&sensor)) return 1;
                set_s16(ICM42688_TEMP_DATA1, 0);
                set_s16(ICM42688_ACCEL_DATA_X1, 8192);
                set_s16(ICM42688_ACCEL_DATA_Y1, -8192);
                set_s16(ICM42688_ACCEL_DATA_Z1, 16384);
                set_s16(ICM42688_GYRO_DATA_X1, 3277);
                set_s16(ICM42688_GYRO_DATA_Y1, -3277);
                set_s16(ICM42688_GYRO_DATA_Z1, 6554);
                cs_low_count = cs_high_count = 0;
                if (!Bsp_Icm42688_Read_Data(&sensor)) return 2;
                if (cs_low_count != 1 || cs_high_count != 1) return 3;
                if (!nearf(sensor.accel_x, 1.0f, 0.001f)) return 4;
                if (!nearf(sensor.accel_y, -1.0f, 0.001f)) return 5;
                if (!nearf(sensor.accel_z, 2.0f, 0.001f)) return 6;
                if (!nearf(sensor.gyro_z, 100.0f, 0.02f)) return 7;
                if (!nearf(sensor.temp, 25.0f, 0.01f)) return 8;
                force_transfer_failure = true;
                if (Bsp_Icm42688_Read_Data(&sensor)) return 9;
                if (sensor.data_valid) return 10;
                return 0;
            }
        ''')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_nonblocking_calibration_and_heading_integration(self):
        result = compile_and_run(r'''
            int main(void)
            {
                imu_sensor_t sensor = make_sensor();
                unsigned i;
                if (!Bsp_Icm42688_Init_Device(&sensor)) return 1;
                set_s16(ICM42688_GYRO_DATA_Z1, 66);
                Bsp_Icm42688_Calibration_Start(&sensor);
                for (i = 0; i < ICM42688_CALIB_SAMPLES; i++) {
                    if (Bsp_Icm42688_Calibration_Update(&sensor) == IMU_CAL_FAILED) return 2;
                }
                if (sensor.calibration_state != IMU_CAL_DONE) return 3;
                if (!nearf(sensor.gyro_z_offset, 66.0f * 500.0f / 32768.0f, 0.001f)) return 4;
                set_s16(ICM42688_GYRO_DATA_Z1, 6620);
                if (!Bsp_Icm42688_Update_Heading(&sensor, 0.005f)) return 5;
                if (!nearf(sensor.gyro_z, 100.0f, 0.03f)) return 6;
                if (!nearf(sensor.heading, 0.5f, 0.002f)) return 7;
                return 0;
            }
        ''')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_sensor_invalid_raw_marker_is_not_reused_as_a_valid_frame(self):
        result = compile_and_run(r'''
            int main(void)
            {
                imu_sensor_t sensor = make_sensor();
                if (!Bsp_Icm42688_Init_Device(&sensor)) return 1;
                set_s16(ICM42688_ACCEL_DATA_X1, INT16_MIN);
                if (Bsp_Icm42688_Read_Data(&sensor)) return 2;
                if (sensor.data_valid) return 3;
                return 0;
            }
        ''')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
