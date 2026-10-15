"""Exercise production AF worker handoff, bounded polling and late completion."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
h=(root/'components/meter_setup/autofocus.h').read_text();cpp=(root/'components/meter_setup/autofocus.cpp').read_text()
source=r'''
#include <atomic>
#include <cstdint>
#include <cassert>
#include <iostream>
#include <map>
uint32_t tick=0;uint32_t millis(){return tick;}
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
using esp_err_t=int;constexpr int ESP_OK=0,ESP_FAIL=-1,ESP_ERR_TIMEOUT=263,ESP_ERR_NO_MEM=257;
constexpr int OV5640_PID=0x5640;
struct sensor_t{struct{int PID=OV5640_PID;}id;int (*set_reg)(sensor_t*,int,int,int);int (*get_reg)(sensor_t*,int,int);};
std::map<int,int> regs{{0x3000,0x85},{0x3602,0x09},{0x3603,0xc0}};int write_error=0;bool read_mismatch=false;
int setreg(sensor_t*,int r,int mask,int v){if(write_error)return -1;regs[r]=(regs[r]&~mask)|(v&mask);return 0;}
int getreg(sensor_t*,int r,int mask){return (regs[r]&mask)^(read_mismatch&&r==0x3602?0x10:0);}
sensor_t sensor{{OV5640_PID},setreg,getreg};sensor_t *esp_camera_sensor_get(){return &sensor;}
enum {ESP_CAMERA_AF_MODE_MANUAL=1};struct esp_camera_af_config_t{int mode;uint16_t step_size,range_min,range_max;uint32_t timeout_ms;};
struct esp_camera_af_status_t{uint8_t raw;bool focused,busy;};
bool supported=true,allocation_ok=true,focus_ok=true;int init_error=0,trigger_error=0,status_error=0,init_calls=0,trigger_calls=0,status_calls=0;
void (*pending)(void*)=nullptr;void *context=nullptr;
int xTaskCreate(void(*fn)(void*),const char*,int stack,void *p,int,void*){assert(stack==5120);if(!allocation_ok)return 0;assert(!pending);pending=fn;context=p;return pdPASS;}
void vTaskDelete(void *p){assert(!p);}void vTaskDelay(uint32_t ms){tick+=ms;}
bool esp_camera_af_is_supported(const sensor_t*){return supported;}
int esp_camera_af_init(sensor_t*,const esp_camera_af_config_t *c){++init_calls;assert(c->mode==ESP_CAMERA_AF_MODE_MANUAL&&c->timeout_ms==2000);return init_error;}
int esp_camera_af_trigger(sensor_t*){++trigger_calls;return trigger_error;}
int esp_camera_af_get_status(sensor_t*,esp_camera_af_status_t *s){++status_calls;s->focused=focus_ok&&status_calls%3==0;s->busy=!s->focused;s->raw=s->focused?0x10:0;return status_error;}
const char *esp_err_to_name(int){return "error";}
void run(){auto fn=pending;auto *p=context;pending=nullptr;assert(fn);fn(p);}
'''+h[h.index('namespace esphome::meter_setup'):]+cpp[cpp.index('namespace esphome::meter_setup'):]+r'''
using namespace esphome::meter_setup;
int main(){
 AutofocusController af;supported=false;assert(!af.start()&&af.state()==AutofocusController::UNSUPPORTED&&!pending);
 supported=true;assert(af.start()&&af.state()==AutofocusController::RUNNING);assert(!af.start());run();assert(af.state()==AutofocusController::FOCUSED&&init_calls==1&&trigger_calls==1&&tick==100);
 assert(af.start());run();assert(af.state()==AutofocusController::FOCUSED&&init_calls==1&&trigger_calls==2);
 auto previous_init=init_calls;af.invalidate();assert(af.start());run();assert(init_calls==previous_init+1);
 focus_ok=false;assert(af.start());auto began=tick;run();assert(af.state()==AutofocusController::FAILED&&af.error()==ESP_ERR_TIMEOUT&&tick-began==4000);
 focus_ok=true;trigger_error=ESP_FAIL;assert(af.start());run();assert(af.state()==AutofocusController::FAILED);trigger_error=0;
 allocation_ok=false;assert(!af.start()&&af.error()==ESP_ERR_NO_MEM&&af.state()==AutofocusController::FAILED);allocation_ok=true;
 assert(af.start());tick+=15001;assert(af.state()==AutofocusController::HUNG&&!af.start());run();assert(af.state()==AutofocusController::HUNG&&!af.start());
 AutofocusController failing;init_error=ESP_FAIL;assert(failing.start());run();assert(failing.state()==AutofocusController::FAILED);init_error=0;assert(failing.start());run();assert(failing.state()==AutofocusController::FOCUSED);
 AutofocusController manual;auto inits=init_calls,triggers=trigger_calls;
 assert(!manual.start_manual(1024)&&!pending);sensor.id.PID=0x3660;assert(!manual.start_manual(300)&&!pending);sensor.id.PID=OV5640_PID;
 assert(manual.start_manual(683));assert(!manual.start());auto began_manual=tick;run();assert(manual.state()==AutofocusController::FOCUSED&&manual.position()==683&&tick-began_manual==100);
 assert(init_calls==inits&&trigger_calls==triggers);assert(regs[0x3000]==0xa5&&regs[0x3602]==0xb9&&regs[0x3603]==0x6a); // Preserve all other MCU/slew/debug bits, clear VCM power-down.
 assert(manual.start());run();assert(init_calls==inits+1&&manual.position()==-1); // Restore AF firmware after a manual job.
 for(auto position:{0,15,16,512,1023}){assert(manual.start_manual(position));run();assert(manual.position()==position&&manual.state()==AutofocusController::FOCUSED);}
 write_error=1;assert(manual.start_manual(100));run();assert(manual.state()==AutofocusController::FAILED&&manual.position()==-1);write_error=0;
 read_mismatch=true;assert(manual.start_manual(100));run();assert(manual.state()==AutofocusController::FAILED&&manual.position()==-1);read_mismatch=false;
 std::cout<<"AF worker passed: manual/single mode, initialization once, asynchronous handoff, status polling, focus timeout, driver/allocation errors, hung task isolation and late-result discard\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-af-worker-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
