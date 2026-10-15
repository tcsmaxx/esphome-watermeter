"""Run the production OV5640 standby controller with register/preferences fakes."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
h=(root/'components/meter_setup/camera_power.h').read_text();cpp=(root/'components/meter_setup/camera_power.cpp').read_text()
source=r'''
#include <cstdint>
#include <string>
#include <map>
#include <vector>
#include <cstring>
#include <cassert>
#include <iostream>
uint32_t tick=100;uint32_t millis(){return tick;}
#define ESP_LOGI(...) ((void)0)
constexpr int OV5640_PID=0x5640;
std::map<int,int> registers{{0x3008,0x02},{0x302c,0xc3}};bool write_fail=false,read_fail=false;int writes=0;
struct sensor_t {struct {int PID=OV5640_PID;}id;int (*set_reg)(sensor_t*,int,int,int);int (*get_reg)(sensor_t*,int,int);};
int set_reg(sensor_t*,int reg,int mask,int value){++writes;if(write_fail)return -1;registers[reg]=(registers[reg]&~mask)|(value&mask);return 0;}
int get_reg(sensor_t*,int reg,int mask){return read_fail?-1:registers[reg]&mask;}
sensor_t sensor{{OV5640_PID},set_reg,get_reg};sensor_t *esp_camera_sensor_get(){return &sensor;}
std::map<uint32_t,std::vector<uint8_t>> storage;bool save_fail=false,sync_fail=false;
struct ESPPreferenceObject {uint32_t key;template<class T>bool load(T *p){auto i=storage.find(key);if(i==storage.end())return false;memcpy(p,i->second.data(),sizeof(T));return true;}template<class T>bool save(const T *p){if(save_fail){save_fail=false;return false;}auto b=reinterpret_cast<const uint8_t*>(p);storage[key]=std::vector<uint8_t>(b,b+sizeof(T));return true;}};
struct Globals{template<class T>ESPPreferenceObject make_preference(uint32_t key){return {key};}bool sync(){if(sync_fail){sync_fail=false;return false;}return true;}}globals;auto *global_preferences=&globals;
'''+h[h.index('namespace esphome::meter_setup'):]+cpp[cpp.index('namespace esphome::meter_setup'):]+r'''
using namespace esphome::meter_setup;
int main(){
 CameraPowerController power;power.setup();assert(power.supported()&&power.standby_enabled()&&!power.weak_drive()&&power.ready());
 tick+=4999;power.loop(false);assert(!power.sleeping());tick++;power.loop(false);assert(power.sleeping()&&registers[0x3008]==0x42);
 power.request();assert(!power.sleeping()&&!power.ready()&&registers[0x3008]==0x02);tick+=299;assert(!power.ready());tick++;assert(power.ready());
 tick+=10000;power.loop(true);assert(!power.sleeping());tick+=5000;power.loop(false);assert(power.sleeping());
 assert(power.configure(false,true));tick+=1000;power.loop(false);assert(power.ready()&&!power.sleeping()&&registers[0x302c]==0x03);tick+=60000;power.loop(false);assert(!power.sleeping());
 assert(power.configure(true,false));tick+=1000;power.loop(true);assert(registers[0x302c]==0xc3);save_fail=true;assert(!power.configure(false,true)&&power.standby_enabled()&&!power.weak_drive());sync_fail=true;assert(!power.configure(false,true)&&power.standby_enabled());
 CameraPowerController restored;restored.setup();assert(restored.standby_enabled()&&!restored.weak_drive());
 tick+=5000;write_fail=true;power.loop(false);assert(!power.sleeping()&&!power.ready());int before=writes;power.request();assert(writes==before);write_fail=false;tick+=1000;power.request();tick+=300;assert(power.ready()&&registers[0x3008]==0x02);
 tick+=5000;read_fail=true;power.loop(false);assert(!power.sleeping()&&!power.ready());read_fail=false;tick+=1000;power.request();tick+=300;assert(power.ready());
 sensor.id.PID=0x3660;before=writes;power.loop(false);power.request();assert(!power.supported()&&power.ready()&&writes==before);
 std::cout<<"Power passed: verified masked standby/wake, 300ms warmup, active holds, weak-drive opt-in and restore, persistence/rollback, bus-error retry, OV3660 no-op\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-power-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
