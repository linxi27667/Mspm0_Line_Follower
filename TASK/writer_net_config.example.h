/**
 * Copy this file to writer_net_config_local.h and edit only that ignored copy.
 * IDs allow only A-Z, a-z, 0-9, underscore, and hyphen (maximum 32 bytes).
 * SSID/password/host fields must not contain quotes, backslashes, CR, or LF.
 */
#ifndef WRITER_NET_CONFIG_LOCAL_H
#define WRITER_NET_CONFIG_LOCAL_H

#define WRITER_NET_ENABLE          (1u)
#define WRITER_NET_DEVICE_ID       "writer-01"
#define WRITER_NET_MQTT_CLIENT_ID  "writer-01-mspm0"

#define WRITER_NET_WIFI_SSID       "replace-me"
#define WRITER_NET_WIFI_PASSWORD   "replace-me"

#define WRITER_NET_BROKER_HOST     "8.134.121.90"
#define WRITER_NET_BROKER_PORT     (1883u)
#define WRITER_NET_BROKER_TLS      (0u)
#define WRITER_NET_MQTT_USERNAME   ""
#define WRITER_NET_MQTT_PASSWORD   ""

#endif /* WRITER_NET_CONFIG_LOCAL_H */
