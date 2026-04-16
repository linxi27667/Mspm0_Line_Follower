#include "ti_msp_dl_config.h"
#include "main.h"
#include "my_easylog.h"

#define DELAY (16000000)

int main(void)
{
    SYSCFG_DL_init();
    my_log_init();
		log_i("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
		log_e("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
		log_w("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
		log_a("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
		log_d("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
		log_v("RTT_INIT", "RTT_VIEW_INIT_SUCCESSFUL");
    while (1) {
        DL_GPIO_clearPins(GPIOB, DL_GPIO_PIN_22);
        log_i("led", "on");
        delay_cycles(DELAY);
        DL_GPIO_setPins(GPIOB, DL_GPIO_PIN_22);
        log_e("led", "off");
        delay_cycles(DELAY);
    }
}