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
#include <memory>
#include <set>
#include <string_view>
#include <vector>

namespace esphome {
namespace sesame_server {

enum class state_t : int8_t { not_connected, connecting, authenticating, running, wait_reboot };

class SesameTrigger;
class SesameTriggerLock : public lock::Lock {
 public:
	SesameTriggerLock(SesameTrigger* parent) : _parent(parent) {};
	void control(const lock::LockCall& call) override;

 private:
	SesameTrigger* _parent;
};

class SesameServerComponent;
class SesameTrigger : public event::Event {
	friend class SesameServerComponent;

 public:
	SesameTrigger(SesameServerComponent* server_component, const char* address);
	void set_history_tag_sensor(text_sensor::TextSensor* sensor) { history_tag_sensor.reset(sensor); }
	void set_trigger_type_sensor(sensor::Sensor* sensor) { trigger_type_sensor.reset(sensor); }
	void set_lock_entity(SesameTriggerLock* lock) {
		lock_entity.reset(lock);
		lock_entity->traits.set_supported_states(trigger_lock_states);
	}
	void set_connection_sensor(binary_sensor::BinarySensor* sensor) {
		connection_sensor.reset(sensor);
		connection_sensor->publish_state(false);
	}
	const NimBLEAddress& get_address() const { return address; }
	libsesame3bt::Sesame::result_code_t invoke(libsesame3bt::Sesame::item_code_t cmd,
	                                           const std::string& tag,
	                                           std::optional<libsesame3bt::trigger_type_t> trigger_type);
	const std::string& get_history_tag() const { return history_tag; }
	float get_trigger_type() const { return trigger_type; }
	bool send_lock_state(lock::LockState state);
	void update_connected(bool connected);

 private:
	NimBLEAddress address;
	SesameServerComponent* server_component;
	std::unique_ptr<text_sensor::TextSensor> history_tag_sensor;
	std::unique_ptr<sensor::Sensor> trigger_type_sensor;
	std::unique_ptr<binary_sensor::BinarySensor> connection_sensor;
	std::unique_ptr<SesameTriggerLock> lock_entity;

	std::string history_tag;
	float trigger_type = NAN;

	static inline const std::set<std::string> supported_triggers{"open", "close", "lock", "unlock"};
	static inline const std::set<lock::LockState> trigger_lock_states{lock::LOCK_STATE_UNLOCKED, lock::LOCK_STATE_LOCKED,
	                                                                  lock::LOCK_STATE_JAMMED};
};

class SesameServerComponent : public Component {
	friend class SesameTrigger;

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

 private:
	libsesame3bt::SesameServer sesame_server;
	const NimBLEUUID uuid;
	std::vector<std::unique_ptr<SesameTrigger>> triggers;
	bool last_status;
	ESPPreferenceObject prefs_secret;

	bool prepare_secret();
	bool save_secret(const std::array<std::byte, libsesame3bt::Sesame::SECRET_SIZE>& secret);
	libsesame3bt::Sesame::result_code_t on_command(const NimBLEAddress& addr,
	                                               libsesame3bt::Sesame::item_code_t cmd,
	                                               const std::string tag,
	                                               std::optional<libsesame3bt::trigger_type_t> trigger_type);
	void on_connected(const NimBLEAddress& addr);
	void on_disconnect(const NimBLEAddress& addr, int reason);
};

}  // namespace sesame_server
}  // namespace esphome
