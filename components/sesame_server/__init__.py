import logging
import string

from esphome import core
import esphome.codegen as cg
from esphome.components import binary_sensor, esp32, event, lock, sensor, text_sensor
import esphome.config_validation as cv
from esphome.const import (
    CONF_ADDRESS,
    CONF_ID,
    CONF_UUID,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_VOLTAGE,
    STATE_CLASS_MEASUREMENT,
    UNIT_PERCENT,
    UNIT_VOLT,
)
from esphome.core import CORE, ID
from esphome.types import ConfigType

_LOGGER = logging.getLogger(__name__)
AUTO_LOAD = ["event", "binary_sensor", "lock", "sensor", "text_sensor"]
DEPENDENCIES = ["esp32", "event", "binary_sensor", "lock", "sensor", "text_sensor"]
CONFLICTS_WITH = ["esp32_ble"]

CONF_TRIGGERS = "triggers"
CONF_MAX_SESSIONS = "max_sessions"
EVENT_TYPES = ["open", "close", "lock", "unlock"]
CONF_LOCK = "lock"
CONF_CONNECTION_SENSOR = "connection_sensor"
CONF_CONNECT_CHECKS = "connect_checks"
CONF_POLICY = "policy"

sesame_server_ns = cg.esphome_ns.namespace("sesame_server")
SesameServerComponent = sesame_server_ns.class_("SesameServerComponent", cg.PollingComponent)
SesameTrigger = sesame_server_ns.class_("SesameTrigger")
StatusLockWrapper = sesame_server_ns.class_("StatusLockWrapper")
SesameServerConnectCheckEntry = sesame_server_ns.class_("SesameServerConnectCheckEntry")
NimBLEAddress = cg.global_ns.class_("NimBLEAddress")
ble_addr_t = cg.global_ns.class_("ble_addr_t")
BLE_ADDR_RANDOM = cg.global_ns.namespace("BLE_ADDR_RANDOM")
BLE_ADDR_PUBLIC = cg.global_ns.namespace("BLE_ADDR_PUBLIC")
connect_check_policy_t = sesame_server_ns.enum("connect_check_policy_t", True)
POLICY_VALUES = {
    "allow": connect_check_policy_t.allow,
    "deny": connect_check_policy_t.deny,
}


CONF_HISTORY_TAG = "history_tag"
CONF_TRIGGER_TYPE = "trigger_type"
CONF_HISTORY_TAG_TYPE = "history_tag_type"
CONF_SCALED_VOLTAGE = "scaled_voltage"
CONF_BATTERY_PCT = "battery_pct"
CONF_SCALED_VOLTAGE2 = "scaled_voltage2"
CONF_BATTERY_PCT2 = "battery_pct2"
CONF_EXTRA = "extra"


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
        _LOGGER.warning("The 'address' option is deprecated and has no effect. It will be removed in the future.")
    return config


def validate_address(config: ConfigType) -> ConfigType:
    if CONF_UUID not in config and CONF_ADDRESS not in config:
        raise cv.RequiredFieldInvalid("Either 'uuid' or 'address' is required")
    return config


def warn_trigger_type_deprecated(config: ConfigType) -> ConfigType:
    if CONF_TRIGGER_TYPE in config:
        if CONF_HISTORY_TAG_TYPE in config:
            raise cv.Invalid("Cannot use both 'trigger_type' and 'history_tag_type' options for triggers. Please use only 'history_tag_type'.")
        config[CONF_HISTORY_TAG_TYPE] = config.pop(CONF_TRIGGER_TYPE)
        _LOGGER.warning(
            "The 'trigger_type' option is deprecated. Please use 'history_tag_type' instead. 'trigger_type' will be removed in the future."
        )
    return config


TRIGGER_SCHEMA = cv.All(
    event.event_schema().extend(
        {
            cv.GenerateID(): cv.declare_id(SesameTrigger),
            cv.Optional(CONF_ADDRESS): cv.mac_address,
            cv.Optional(CONF_UUID): cv.uuid,
            cv.Optional(CONF_HISTORY_TAG): text_sensor.text_sensor_schema(),
            cv.Optional(CONF_TRIGGER_TYPE): sensor.sensor_schema(),
            cv.Optional(CONF_HISTORY_TAG_TYPE): sensor.sensor_schema(),
            cv.Optional(CONF_SCALED_VOLTAGE): sensor.sensor_schema(
                unit_of_measurement=UNIT_VOLT,
                device_class=DEVICE_CLASS_VOLTAGE,
                state_class=STATE_CLASS_MEASUREMENT,
                accuracy_decimals=2,
            ),
            cv.Optional(CONF_BATTERY_PCT): sensor.sensor_schema(
                unit_of_measurement=UNIT_PERCENT,
                device_class=DEVICE_CLASS_BATTERY,
                state_class=STATE_CLASS_MEASUREMENT,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_SCALED_VOLTAGE2): sensor.sensor_schema(
                unit_of_measurement=UNIT_VOLT,
                device_class=DEVICE_CLASS_VOLTAGE,
                state_class=STATE_CLASS_MEASUREMENT,
                accuracy_decimals=2,
            ),
            cv.Optional(CONF_BATTERY_PCT2): sensor.sensor_schema(
                unit_of_measurement=UNIT_PERCENT,
                device_class=DEVICE_CLASS_BATTERY,
                state_class=STATE_CLASS_MEASUREMENT,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_EXTRA): text_sensor.text_sensor_schema(),
            cv.Optional(CONF_LOCK): cv.use_id(lock.Lock),
            cv.Optional(CONF_CONNECTION_SENSOR): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_CONNECTIVITY,
            ),
        }
    ),
    validate_address,
    warn_trigger_type_deprecated,
)


def validate_connect_checks(config):
    if config[-1][CONF_ADDRESS] != "any" or any(ent[CONF_ADDRESS] == "any" for ent in config[0:-1]):
        raise cv.Invalid(f"The {CONF_CONNECT_CHECKS} list must contain 'any' as the only and final entry.")
    if config[-1][CONF_POLICY] not in ("allow", "deny"):
        raise cv.Invalid(f"Invalid policy for 'any' entry in {CONF_CONNECT_CHECKS} list. Must be 'allow' or 'deny'.")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SesameServerComponent),
            cv.Required(CONF_UUID): cv.uuid,
            cv.Optional(CONF_ADDRESS): cv.string,
            cv.Optional(CONF_MAX_SESSIONS, default=3): cv.int_range(1, 9),
            cv.Optional(CONF_TRIGGERS): cv.ensure_list(TRIGGER_SCHEMA),
            cv.Optional(CONF_LOCK): cv.use_id(lock.Lock),
            cv.Optional(CONF_CONNECT_CHECKS): cv.All(
                cv.ensure_list(
                    cv.Schema(
                        {
                            cv.Required(CONF_ADDRESS): cv.Any(cv.one_of("any"), cv.mac_address),
                            cv.Required(CONF_POLICY): cv.enum(POLICY_VALUES),
                        }
                    )
                ),
                cv.Length(min=1),
                validate_connect_checks,
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    warn_address_deprecated,
)


def mac_to_ints(mac) -> list[int]:
    return [int(x, 16) for x in str(mac).split(":")]


async def to_connect_checks_code(server, config):
    if len(config) == 0:
        return
    cg.add_global(cg.RawStatement("#include <NimBLEAddress.h>"), prepend=True)
    svarid = ID(f"{server.base}_connect_checks", is_declaration=True, type=SesameServerConnectCheckEntry)
    checks = []
    zeros = [0] * 6
    for entry in config:
        address = zeros if entry[CONF_ADDRESS] == "any" else list(reversed(mac_to_ints(entry[CONF_ADDRESS])))
        policy = entry[CONF_POLICY]
        checks.append({"address": address, "policy": policy})
    initializer = [
        SesameServerConnectCheckEntry(
            NimBLEAddress()
            if check["address"] == zeros
            else NimBLEAddress(cg.StructInitializer(ble_addr_t, ("type", BLE_ADDR_RANDOM), ("val", check["address"]))),
            check["policy"],
        )
        for check in checks
    ]
    svar = cg.static_const_array(svarid, initializer)
    cg.add(server.set_connect_checks(svar))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID], config[CONF_MAX_SESSIONS], str(config[CONF_UUID]))
    if CONF_CONNECT_CHECKS in config:
        await to_connect_checks_code(var, config[CONF_CONNECT_CHECKS])
    if CONF_LOCK in config:
        lock = await cg.get_variable(config[CONF_LOCK])
        cg.add(var.set_lock_entity(lock))
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
            if CONF_HISTORY_TAG_TYPE in tconf:
                t = await sensor.new_sensor(tconf[CONF_HISTORY_TAG_TYPE])
                cg.add(trig.set_history_tag_type_sensor(t))
            if CONF_SCALED_VOLTAGE in tconf:
                s = await sensor.new_sensor(tconf[CONF_SCALED_VOLTAGE])
                cg.add(trig.set_scaled_voltage_sensor(s))
            if CONF_BATTERY_PCT in tconf:
                s = await sensor.new_sensor(tconf[CONF_BATTERY_PCT])
                cg.add(trig.set_battery_pct_sensor(s))
            if CONF_SCALED_VOLTAGE2 in tconf:
                s = await sensor.new_sensor(tconf[CONF_SCALED_VOLTAGE2])
                cg.add(trig.set_scaled_voltage2_sensor(s))
            if CONF_BATTERY_PCT2 in tconf:
                s = await sensor.new_sensor(tconf[CONF_BATTERY_PCT2])
                cg.add(trig.set_battery_pct2_sensor(s))
            if CONF_EXTRA in tconf:
                s = await text_sensor.new_text_sensor(tconf[CONF_EXTRA])
                cg.add(trig.set_extra_sensor(s))
            if CONF_LOCK in tconf:
                lock = await cg.get_variable(tconf[CONF_LOCK])
                cg.add(trig.set_lock_entity(lock))
            if CONF_CONNECTION_SENSOR in tconf:
                bconf = tconf[CONF_CONNECTION_SENSOR]
                bs = await binary_sensor.new_binary_sensor(bconf)
                cg.add(trig.set_connection_sensor(bs))
            cg.add(var.add_trigger(trig))
        for trig, tconf in triggers:
            await event.register_event(trig, tconf, event_types=EVENT_TYPES)

    cg.add_library("libsesame3bt-server", None, "https://github.com/homy-newfs8/libsesame3bt-server#v0.13.3")
    # cg.add_library("libsesame3bt-server", None, "symlink://../../../../libsesame3bt-server")
    # cg.add_library("libsesame3bt-core", None, "symlink://../../../../libsesame3bt-core")
    # cg.add_platformio_option("lib_ldf_mode", "deep")

    if not CORE.using_arduino:
        esp32.add_idf_component(name="h2zero/esp-nimble-cpp", ref="~2.5.0")
        CORE.add_platformio_option("lib_ignore", "NimBLE-Arduino")
