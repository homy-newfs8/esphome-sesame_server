import string

import esphome.codegen as cg
from esphome.components import event, sensor, text_sensor
import esphome.config_validation as cv
from esphome.const import CONF_ADDRESS, CONF_ID, CONF_UUID

AUTO_LOAD = ["event", "sensor", "text_sensor"]
DEPENDENCIES = ["event", "sensor", "text_sensor"]
CONFLICTS_WITH = ["esp32_ble"]

CONF_TRIGGERS = "triggers"
CONF_MAX_SESSIONS = "max_sessions"
EVENT_TYPES = ["open", "close", "lock", "unlock"]

sesame_server_ns = cg.esphome_ns.namespace("sesame_server")
SesameServerComponent = sesame_server_ns.class_("SesameServerComponent", cg.PollingComponent)
SesameTrigger = sesame_server_ns.class_("SesameTrigger")

CONF_HISTORY_TAG = "history_tag"
CONF_TRIGGER_TYPE = "trigger_type"


def is_hex_string(str, valid_len):
    return len(str) == valid_len and all(c in string.hexdigits for c in str)


def valid_hexstring(key, valid_len):
    def func(str):
        if is_hex_string(str, valid_len):
            return str
        else:
            raise cv.Invalid(f"'{key}' must be a {valid_len} bytes hex string")

    return func


TRIGGER_SCHEMA = event.event_schema().extend(
    {
        cv.GenerateID(): cv.declare_id(SesameTrigger),
        cv.Required(CONF_ADDRESS): cv.mac_address,
        cv.Optional(CONF_HISTORY_TAG): text_sensor.text_sensor_schema(),
        cv.Optional(CONF_TRIGGER_TYPE): sensor.sensor_schema(),
    }
)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SesameServerComponent),
            cv.Required(CONF_UUID): cv.uuid,
            cv.Required(CONF_ADDRESS): cv.mac_address,
            cv.Optional(CONF_MAX_SESSIONS, default=3): cv.int_range(1, 9),
            cv.Optional(CONF_TRIGGERS): cv.ensure_list(TRIGGER_SCHEMA),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_with_arduino,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID], config[CONF_MAX_SESSIONS], str(config[CONF_UUID]), str(config[CONF_ADDRESS]))
    await cg.register_component(var, config)
    if CONF_TRIGGERS in config:
        for trigger in config[CONF_TRIGGERS]:
            trig = cg.new_Pvariable(trigger[CONF_ID], str(trigger[CONF_ADDRESS]))
            await event.register_event(trig, trigger, event_types=EVENT_TYPES)
            if CONF_HISTORY_TAG in trigger:
                t = await text_sensor.new_text_sensor(trigger[CONF_HISTORY_TAG])
                cg.add(trig.set_history_tag_sensor(t))
            if CONF_TRIGGER_TYPE in trigger:
                t = await sensor.new_sensor(trigger[CONF_TRIGGER_TYPE])
                cg.add(trig.set_trigger_type_sensor(t))
            cg.add(var.add_trigger(trig))
    cg.add_library("libsesame3bt-server", None, "https://github.com/homy-newfs8/libsesame3bt-server#v0.5.0")
    # cg.add_library("libsesame3bt-server", None, "symlink://../../../../../../PlatformIO/Projects/libsesame3bt-server")
    # cg.add_library("libsesame3bt-core", None, "symlink://../../../../../../PlatformIO/Projects/libsesame3bt-core")
    # cg.add_platformio_option("lib_ldf_mode", "deep")
