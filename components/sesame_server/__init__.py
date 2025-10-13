import logging
import string

import esphome.codegen as cg
from esphome.components import binary_sensor, event, lock, sensor, text_sensor
import esphome.config_validation as cv
from esphome.const import CONF_ADDRESS, CONF_ID, CONF_UUID, DEVICE_CLASS_CONNECTIVITY
from esphome.types import ConfigType

_LOGGER = logging.getLogger(__name__)
AUTO_LOAD = ["event", "binary_sensor", "sensor", "text_sensor", "lock"]
DEPENDENCIES = ["event", "binary_sensor", "sensor", "text_sensor", "lock"]
CONFLICTS_WITH = ["esp32_ble"]

CONF_TRIGGERS = "triggers"
CONF_MAX_SESSIONS = "max_sessions"
EVENT_TYPES = ["open", "close", "lock", "unlock"]
CONF_LOCK = "lock"
CONF_CONNECTION_SENSOR = "connection_sensor"

sesame_server_ns = cg.esphome_ns.namespace("sesame_server")
SesameServerComponent = sesame_server_ns.class_("SesameServerComponent", cg.PollingComponent)
SesameTrigger = sesame_server_ns.class_("SesameTrigger")
StatusLock = sesame_server_ns.class_("StatusLock", lock.Lock)

CONF_HISTORY_TAG = "history_tag"
CONF_TRIGGER_TYPE = "trigger_type"


def is_hex_string(str, valid_len):
    return len(str) == valid_len and all(c in string.hexdigits for c in str)


def valid_hexstring(key, valid_len):
    def func(str):
        if is_hex_string(str, valid_len):
            return str
        raise cv.Invalid(f"'{key}' must be a {valid_len} bytes hex string")

    return func


def warn_address_deprecated(config: ConfigType) -> ConfigType:
    if CONF_ADDRESS in config:
        _LOGGER.warning(
            "The 'address' option for esphome-sesame_server components is deprecated and has no effect. It will be removed in the future."
        )
    return config


def validate_address(config: ConfigType) -> ConfigType:
    if CONF_UUID not in config and CONF_ADDRESS not in config:
        raise cv.RequiredFieldInvalid("Either 'uuid' or 'address' is required")
    return config


TRIGGER_SCHEMA = cv.All(
    event.event_schema().extend(
        {
            cv.GenerateID(): cv.declare_id(SesameTrigger),
            cv.Optional(CONF_ADDRESS): cv.mac_address,
            cv.Optional(CONF_UUID): cv.uuid,
            cv.Optional(CONF_HISTORY_TAG): text_sensor.text_sensor_schema(),
            cv.Optional(CONF_TRIGGER_TYPE): sensor.sensor_schema(),
            cv.Optional(CONF_LOCK): lock.lock_schema().extend(
                {
                    cv.GenerateID(): cv.declare_id(StatusLock),
                }
            ),
            cv.Optional(CONF_CONNECTION_SENSOR): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_CONNECTIVITY,
            ),
        }
    ),
    validate_address,
)


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SesameServerComponent),
            cv.Required(CONF_UUID): cv.uuid,
            cv.Optional(CONF_ADDRESS): cv.string,
            cv.Optional(CONF_MAX_SESSIONS, default=3): cv.int_range(1, 9),
            cv.Optional(CONF_TRIGGERS): cv.ensure_list(TRIGGER_SCHEMA),
            cv.Optional(CONF_LOCK): lock.lock_schema().extend(
                {
                    cv.GenerateID(): cv.declare_id(StatusLock),
                }
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_with_arduino,
    warn_address_deprecated,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID], config[CONF_MAX_SESSIONS], str(config[CONF_UUID]))
    if CONF_LOCK in config:
        lconf = config[CONF_LOCK]
        lck = cg.new_Pvariable(lconf[CONF_ID], var)
        await lock.register_lock(lck, lconf)
        cg.add(var.set_lock_entity(lck))
    await cg.register_component(var, config)
    if CONF_TRIGGERS in config:
        triggers = []
        for tconf in config[CONF_TRIGGERS]:
            address = tconf.get(CONF_ADDRESS) or ""
            uuid = tconf.get(CONF_UUID) or ""
            trig = cg.new_Pvariable(tconf[CONF_ID], var, str(address), str(uuid))
            triggers.append((trig, tconf))
            if CONF_HISTORY_TAG in tconf:
                t = await text_sensor.new_text_sensor(tconf[CONF_HISTORY_TAG])
                cg.add(trig.set_history_tag_sensor(t))
            if CONF_TRIGGER_TYPE in tconf:
                t = await sensor.new_sensor(tconf[CONF_TRIGGER_TYPE])
                cg.add(trig.set_trigger_type_sensor(t))
            if CONF_LOCK in tconf:
                lconf = tconf[CONF_LOCK]
                lck = cg.new_Pvariable(lconf[CONF_ID], trig)
                await lock.register_lock(lck, lconf)
                cg.add(trig.set_lock_entity(lck))
            if CONF_CONNECTION_SENSOR in tconf:
                bconf = tconf[CONF_CONNECTION_SENSOR]
                bs = await binary_sensor.new_binary_sensor(bconf)
                await binary_sensor.register_binary_sensor(bs, bconf)
                cg.add(trig.set_connection_sensor(bs))
            cg.add(var.add_trigger(trig))
        for trig, tconf in triggers:
            await event.register_event(trig, tconf, event_types=EVENT_TYPES)

    # cg.add_library("libsesame3bt-server", None, "https://github.com/homy-newfs8/libsesame3bt-server#v0.8.0")
    cg.add_library("libsesame3bt-server", None, "symlink://../../../../../../PlatformIO/Projects/libsesame3bt-server")
    cg.add_library("libsesame3bt-core", None, "symlink://../../../../../../PlatformIO/Projects/libsesame3bt-core")
    cg.add_platformio_option("lib_ldf_mode", "deep")
