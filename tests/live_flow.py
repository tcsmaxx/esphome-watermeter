"""Exercise production debug-stream start, restoration, timeout and failure handling."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
flow=cpp[cpp.index('void MeterSetup::live_loop_('):cpp.index('void MeterSetup::update_status_(')]
stop=cpp[cpp.index('void MeterSetup::stop_live_('):cpp.index('void MeterSetup::handleRequest(')]
source=r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <iostream>
uint32_t clock_ms=100;uint32_t millis(){return clock_ms;}
namespace camera {enum CameraRequester{WEB_REQUESTER};}
struct Camera {int stops=0;void stop_stream(camera::CameraRequester){++stops;}};
struct MeterSetup {
 bool live_=false,live_streaming_=false,live_was_paused_=true,paused_=false,capture_pending_=false,inference_started_=false,light_test_=false,lamp=false;
 uint8_t capture_stage_=0;
 uint32_t live_deadline_=0,live_last_frame_=0,live_frame_at_=0,frame_=0,next_=0;
 struct Settings{uint32_t interval=60;}settings_;int pending_illumination_=0;
 std::string message_;Camera camera;Camera *camera_=&camera;
 void begin_capture_(bool inference){assert(!inference);capture_pending_=true;lamp=true;}
 void set_illumination_(bool on,int){lamp=on;}
 void live_loop_(bool,bool);void stop_live_();
};
'''+flow+stop+r'''
int main(){
 MeterSetup m;m.live_loop_(true,false);assert(m.live_&&m.paused_&&m.capture_pending_&&m.lamp);
 m.capture_pending_=false;m.live_streaming_=true;m.live_frame_at_=clock_ms;m.live_loop_(false,false);assert(m.live_);
 clock_ms+=9999;m.live_loop_(false,false);assert(m.live_);m.frame_++;m.live_loop_(false,false);clock_ms+=9999;m.live_loop_(false,false);assert(m.live_);
 clock_ms+=2;m.live_loop_(false,false);assert(!m.live_&&!m.paused_&&!m.lamp&&m.camera.stops==1&&m.message_.find("10 Sekunden")!=std::string::npos);
 m.paused_=true;m.live_loop_(true,false);m.live_loop_(false,true);assert(!m.live_&&m.paused_&&!m.capture_pending_);
 m.paused_=false;m.live_loop_(true,false);clock_ms+=120000;m.live_loop_(false,false);assert(!m.live_&&!m.paused_&&!m.lamp);
 m.live_loop_(true,false);m.capture_pending_=false;m.message_="Fokus nicht gefunden";m.live_loop_(false,false);assert(!m.live_&&!m.paused_&&m.message_.find("Fokus nicht gefunden")!=std::string::npos);
 m.live_loop_(true,false);m.live_loop_(false,true);assert(!m.live_&&!m.capture_pending_&&!m.lamp); // Stop during focus preparation.
 m.capture_stage_=3;m.live_loop_(true,false);m.live_loop_(false,true);assert(!m.live_&&m.capture_pending_&&m.lamp); // Preserve supervision of a running AF task.
 std::cout<<"Live flow passed: pause/restore, frame heartbeat, 10-second stall, 2-minute limit, focus failure and stop during preparation\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-live-') as tmp:
 binary=str(Path(tmp)/'test')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
