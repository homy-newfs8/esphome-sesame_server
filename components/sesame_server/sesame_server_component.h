#pragma once
#include <NimBLEDevice.h>
#include <SesameServer.h>
#include <esphome/components/binary_sensor/binary_sensor.h>
#include <esphome/components/event/event.h>
#include <esphome/components/lock/lock.h>
#include <esphome/components/sensor/sensor.h>
#include <esphome/components/text_sensor/text_sensor.h>
#include <esphome/core/component.h>
#include <esphome/core/preferences.h>
#include <esphome/core/version.h>
#include <functional>
#include <memory>
#include <set>
#include <string_view>
#include <variant>
#include <vector>

namespace esphome {
namespace sesame_server {

enum class state_t : int8_t { not_connected, connecting, authenticating, running, wait_reboot };

class SesameTrigger;
class SesameServerComponent;
class StatusLockWrapper {
 public:
	StatusLockWrapper(lock::Lock& lock, SesameTrigger& trigger) : lock_(lock), parent_(trigger) { init(); }
	StatusLockWrapper(lock::Lock& lock, SesameServerComponent& trigger) : lock_(lock), parent_(trigger) { init(); }
	lock::LockState get_state() const { return lock_.state; }

 private:
	void init();
	lock::Lock& lock_;
	std::variant<std::reference_wrapper<SesameTrigger>, std::reference_wrapper<SesameServerComponent>> parent_;
};

class SesameServerComponent;
class SesameTrigger : public event::Event {
 public:
	SesameTrigger(SesameServerComponent* server_component, std::string_view addr, std::string_view uuid);
	void set_history_tag_sensor(text_sensor::TextSensor* sensor) { history_tag_sensor.reset(sensor); }
	void set_history_tag_type_sensor(sensor::Sensor* sensor) { history_tag_type_sensor.reset(sensor); }
	void set_lock_entity(lock::Lock* lock) { lock_entity = std::make_unique<StatusLockWrapper>(*lock, *this); }
	void set_connection_sensor(binary_sensor::BinarySensor* sensor) {
		connection_sensor.reset(sensor);
		connection_sensor->publish_state(false);
	}
	const NimBLEAddress& get_address() const { return address; }
	void invoke(libsesame3bt::Sesame::item_code_t cmd,
	            const std::string& tag,
	            std::optional<libsesame3bt::history_tag_type_t> history_tag_type);
	const std::string& get_history_tag() const { return history_tag; }
	[[deprecated("Use get_history_tag_type() instead")]]
	float get_trigger_type() const {
		return history_tag_type;
	}
	float get_history_tag_type() const { return history_tag_type; }
	bool send_lock_state(lock::LockState state);
	void update_connected(bool connected);
	bool has_lock_entity() const { return lock_entity != nullptr; }

 private:
	NimBLEAddress address;
	SesameServerComponent* server_component;
	std::unique_ptr<text_sensor::TextSensor> history_tag_sensor;
	std::unique_ptr<sensor::Sensor> history_tag_type_sensor;
	std::unique_ptr<binary_sensor::BinarySensor> connection_sensor;
	std::unique_ptr<StatusLockWrapper> lock_entity;

	std::string history_tag;
	float history_tag_type = NAN;
#if ESPHOME_VERSION_CODE < VERSION_CODE(2025, 11, 0)
	static inline const std::set<std::string> supported_triggers{"open", "close", "lock", "unlock"};
#endif
};

class SesameServerComponent : public Component {
 public:
	SesameServerComponent(uint8_t max_sessions, std::string_view uuid);
	void setup() override;
	void loop() override;
	void reset();
	void add_trigger(SesameTrigger* trigger) {
		auto p = std::unique_ptr<SesameTrigger>(trigger);
		triggers.push_back(std::move(p));
	}
	virtual float get_setup_priority() const override { return setup_priority::AFTER_WIFI; };
	void disconnect(const NimBLEAddress& addr);
	bool has_session(const NimBLEAddress& addr) const;
	bool has_trigger(const NimBLEAddress& addr) const;
	void start_advertising();
	void stop_advertising();
	void set_lock_entity(lock::Lock* lock) { lock_entity = std::make_unique<StatusLockWrapper>(*lock, *this); }
	bool send_lock_state(lock::LockState state);
	bool send_lock_state(const NimBLEAddress* dest, lock::LockState state);
	bool send_current_lock_state(const NimBLEAddress& address);

 private:
	libsesame3bt::SesameServer sesame_server;
	const NimBLEUUID uuid;
	std::vector<std::unique_ptr<SesameTrigger>> triggers;
	ESPPreferenceObject prefs_secret;
	std::unique_ptr<StatusLockWrapper> lock_entity;

	bool prepare_secret();
	bool save_secret(const std::array<std::byte, libsesame3bt::Sesame::SECRET_SIZE>& secret);
	void on_command(const NimBLEAddress& addr,
	                libsesame3bt::Sesame::item_code_t cmd,
	                const std::string tag,
	                std::optional<libsesame3bt::history_tag_type_t> history_tag_type);
	void on_connected(const NimBLEAddress& addr);
	void on_disconnect(const NimBLEAddress& addr, int reason);
};

}  // namespace sesame_server
}  // namespace esphome
