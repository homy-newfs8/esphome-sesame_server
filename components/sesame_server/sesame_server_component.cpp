#include "sesame_server_component.h"
#include <Arduino.h>
#include <esphome/core/application.h>
#include <esphome/core/log.h>

namespace esphome::sesame_server {

namespace {

constexpr const char TAG[] = "sesame_server";

constexpr const uint32_t SESAMESERVER_RANDOM = 0x76d18970;

}  // namespace

using libsesame3bt::Sesame;
using libsesame3bt::SesameServer;

static const char*
event_name(Sesame::item_code_t cmd) {
	using item_code_t = Sesame::item_code_t;
	switch (cmd) {
		case item_code_t::lock:
			return "lock";
		case item_code_t::unlock:
			return "unlock";
		case item_code_t::door_open:
			return "open";
		case item_code_t::door_closed:
			return "close";
			break;
		default:
			return "";
	}
}

SesameServerComponent::SesameServerComponent(uint8_t max_sessions, std::string_view uuid)
    : sesame_server(max_sessions), uuid(std::string{uuid}) {}

bool
SesameServerComponent::prepare_secret() {
	prefs_secret = global_preferences->make_preference<std::array<std::byte, Sesame::SECRET_SIZE>>(SESAMESERVER_RANDOM);
	std::array<std::byte, Sesame::SECRET_SIZE> secret;
	if (prefs_secret.load(&secret)) {
		if (std::any_of(std::cbegin(secret), std::cend(secret), [](auto x) { return x != std::byte{0}; })) {
			if (!sesame_server.set_registered(secret)) {
				ESP_LOGE(TAG, "Failed to restore secret");
				return false;
			}
		}
	}
	return true;
}

bool
SesameServerComponent::save_secret(const std::array<std::byte, Sesame::SECRET_SIZE>& secret) {
	if (prefs_secret.save(&secret) && global_preferences->sync()) {
		return true;
	}
	ESP_LOGE(TAG, "Failed to store secret");
	return false;
}

Sesame::result_code_t
SesameServerComponent::on_command(const NimBLEAddress& addr,
                                  Sesame::item_code_t cmd,
                                  const std::string tag,
                                  std::optional<libsesame3bt::trigger_type_t> trigger_type) {
	ESP_LOGD(TAG, "cmd=%s(%u), tag=\"%s\" received from %s", event_name(cmd), static_cast<uint8_t>(cmd), tag.c_str(),
	         addr.toString().c_str());
	if (auto trig = std::find_if(std::cbegin(triggers), std::cend(triggers),
	                             [&addr](const auto& trigger) { return trigger->get_address() == addr; });
	    trig == std::cend(triggers)) {
		ESP_LOGW(TAG, "%s: cmd=%s(%u), tag=\"%s\" received from unlisted device", addr.toString().c_str(), event_name(cmd),
		         static_cast<uint8_t>(cmd), tag.c_str());
		return Sesame::result_code_t::success;
	} else {
		if (!(*trig)->lock_entity) {
			if (cmd == Sesame::item_code_t::lock || cmd == Sesame::item_code_t::unlock) {
				last_status = cmd == Sesame::item_code_t::lock;
				set_timeout(0, [this]() {
					if (!sesame_server.send_lock_status(last_status)) {
						ESP_LOGW(TAG, "Failed to send lock status");
					}
				});
			}
		}
		return (*trig)->invoke(cmd, tag, trigger_type);
	}
}

void
SesameServerComponent::setup() {
	if (!prepare_secret()) {
		mark_failed();
		return;
	}
	if (!sesame_server.is_registered()) {
		sesame_server.set_on_registration_callback([this](const auto& addr, const auto& secret) {
			this->save_secret(secret);
			ESP_LOGI(TAG, "SESAME registered by %s", addr.toString().c_str());
		});
	}
	sesame_server.set_on_command_callback([this](const auto& addr, auto item_code, const auto& tag, auto trigger_type) {
		defer([this, addr, item_code, tag_str = tag, trigger_type]() { on_command(addr, item_code, tag_str, trigger_type); });
		return Sesame::result_code_t::success;
	});
	sesame_server.set_on_connect_callback([this](const auto& addr) { defer([this, addr]() { on_connected(addr); }); });
	sesame_server.set_on_disconnect_callback(
	    [this](const auto& addr, int reason) { defer([this, addr, reason]() { on_disconnect(addr, reason); }); });
	if (!sesame_server.begin(Sesame::model_t::sesame_5, uuid) || !sesame_server.start_advertising()) {
		ESP_LOGE(TAG, "Failed to start SESAME server");
		mark_failed();
		return;
	}
	ESP_LOGI(TAG, "SESAME Server started as %sregistered on %s", sesame_server.is_registered() ? "" : "not ",
	         NimBLEDevice::getAddress().toString().c_str());
}

void
SesameServerComponent::loop() {
	sesame_server.update();
}

void
SesameServerComponent::reset() {
	std::array<std::byte, Sesame::SECRET_SIZE> secret{};
	if (prefs_secret.save(&secret) && global_preferences->sync()) {
		ESP_LOGI(TAG, "Reset done, restarting...");
		App.safe_reboot();
	} else {
		ESP_LOGE(TAG, "Failed to erase secret");
		mark_failed();
	}
}

SesameTrigger::SesameTrigger(SesameServerComponent* server_component, const char* address)
    : address(address, BLE_ADDR_RANDOM), server_component(server_component) {
	set_event_types(supported_triggers);
}

static float
make_float(std::optional<libsesame3bt::trigger_type_t> trigger_type) {
	if (trigger_type.has_value()) {
		return static_cast<float>(*trigger_type);
	}
	return NAN;
}

Sesame::result_code_t
SesameTrigger::invoke(Sesame::item_code_t cmd, const std::string& tag, std::optional<libsesame3bt::trigger_type_t> trigger_type) {
	const char* evs = event_name(cmd);
	if (evs[0] == 0) {
		return Sesame::result_code_t::unknown;
	}
	history_tag = tag;
	this->trigger_type = make_float(trigger_type);
	if (history_tag_sensor) {
		history_tag_sensor->publish_state(tag);
	}
	if (trigger_type_sensor) {
		trigger_type_sensor->publish_state(this->trigger_type);
	}
	ESP_LOGD(TAG, "Triggering %s to %s", evs, get_name().c_str());
	trigger(evs);
	return Sesame::result_code_t::success;
}

void
SesameServerComponent::disconnect(const NimBLEAddress& addr) {
	if (has_session(addr)) {
		ESP_LOGI(TAG, "Disconnecting %s", addr.toString().c_str());
		sesame_server.disconnect(addr);
	}
}

bool
SesameServerComponent::has_session(const NimBLEAddress& addr) const {
	return sesame_server.has_session(addr);
}

bool
SesameServerComponent::has_trigger(const NimBLEAddress& addr) const {
	return std::any_of(std::cbegin(triggers), std::cend(triggers),
	                   [&addr](const auto& trigger) { return trigger->get_address() == addr; });
}

void
SesameServerComponent::start_advertising() {
	if (!sesame_server.start_advertising()) {
		ESP_LOGW(TAG, "Failed to start advertising");
	}
}

void
SesameServerComponent::stop_advertising() {
	if (!sesame_server.stop_advertising()) {
		ESP_LOGW(TAG, "Failed to stop advertising");
	}
}

void
SesameTriggerLock::control(const lock::LockCall& call) {
	ESP_LOGD(TAG, "Sesame Server Trigger Lock control state = %s",
	         call.get_state().has_value() ? lock_state_to_string(*call.get_state()) : "none");
	if (!call.get_state().has_value()) {
		ESP_LOGW(TAG, "LockCall without state, ignored");
		return;
	}
	this->state = *call.get_state();

	if (!_parent->send_lock_state(this->state)) {
		ESP_LOGW(TAG, "Failed to send lock status");
	}
	publish_state(this->state);
}

bool
SesameTrigger::send_lock_state(lock::LockState state) {
	ESP_LOGD(TAG, "Sending lock state %s to trigger", lock::lock_state_to_string(state));
	Sesame::mecha_status_5_t sst{};
	sst.is_stop = true;
	sst.battery = 10.0f;  // dummy voltage
	if (state == lock::LOCK_STATE_JAMMED) {
		sst.is_critical = true;
		sst.in_lock = false;
	} else {
		sst.in_lock = state == lock::LOCK_STATE_LOCKED;
	}
	if (server_component->sesame_server.has_session(address)) {
		return server_component->sesame_server.send_mecha_status(&address, sst);
	} else {
		ESP_LOGW(TAG, "No session, cannot send lock status");
		return false;
	}
}

void
SesameServerComponent::on_connected(const NimBLEAddress& addr) {
	ESP_LOGI(TAG, "%s connected", addr.toString().c_str());
	if (auto trig = std::find_if(std::cbegin(triggers), std::cend(triggers),
	                             [&addr](const auto& trigger) { return trigger->get_address() == addr; });
	    trig != std::cend(triggers)) {
		(*trig)->update_connected(true);
	}
}

void
SesameServerComponent::on_disconnect(const NimBLEAddress& addr, int reason) {
	ESP_LOGI(TAG, "%s disconnected, reason=%d", addr.toString().c_str(), reason);
	if (auto trig = std::find_if(std::cbegin(triggers), std::cend(triggers),
	                             [&addr](const auto& trigger) { return trigger->get_address() == addr; });
	    trig != std::cend(triggers)) {
		(*trig)->update_connected(false);
	}
}

void
SesameTrigger::update_connected(bool connected) {
	if (connection_sensor) {
		connection_sensor->publish_state(connected);
	}
	if (connected) {
		if (lock_entity) {
			send_lock_state(lock_entity->state);
		}
	}
}

}  // namespace esphome::sesame_server
