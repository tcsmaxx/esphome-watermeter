"""Test production annotation, camera proxy and readers against codec/hardware fakes.
The codec declarations come from the pinned Espressif component; this does not
replace a hardware JPEG encoder integration test.
"""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
header=(root/'components/meter_setup/timestamp_camera.h').read_text()
cpp=(root/'components/meter_setup/timestamp_camera.cpp').read_text()
body=header[header.index('namespace esphome::meter_setup'):]+cpp[cpp.index('namespace esphome::meter_setup'):]
source=r'''
#include <cassert>
#include <ctime>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <memory>
#include <vector>
#include <string>
#include <algorithm>
#include <iostream>
#include <sys/time.h>
#include "esp_jpeg_dec.h"
#include "esp_jpeg_enc.h"
#define MALLOC_CAP_SPIRAM 0
#define MALLOC_CAP_8BIT 0
#define ESP_LOGW(...) ((void)0)
void *heap_caps_aligned_alloc(size_t a,size_t n,int){void *p=nullptr;return posix_memalign(&p,a,n)==0?p:nullptr;}
void heap_caps_free(void *p){free(p);}
int64_t esp_timer_get_time(){return 10000000;}
namespace esphome {
struct EntityBase{std::string name="Kamerabild";uint32_t hash=7654;bool internal=false;};
namespace meter_setup {struct CameraPowerController{int requests=0;bool awake=true;void request(){++requests;}bool ready(){return awake;}};}
namespace setup_priority {constexpr float IO=900;}
namespace camera {
enum CameraRequester{IDLE,API_REQUESTER,WEB_REQUESTER};
struct CameraImage {virtual uint8_t *get_data_buffer()=0;virtual size_t get_data_length()=0;virtual bool was_requested_by(CameraRequester)const=0;virtual ~CameraImage()=default;};
struct CameraListener {virtual void on_camera_image(const std::shared_ptr<CameraImage>&){};virtual void on_stream_start(){};virtual void on_stream_stop(){}};
struct CameraImageReader {virtual void set_image(std::shared_ptr<CameraImage>)=0;virtual size_t available()const=0;virtual uint8_t *peek_data_buffer()=0;virtual void consume_data(size_t)=0;virtual void return_image()=0;virtual ~CameraImageReader()=default;};
struct Camera:EntityBase {
 Camera(){assert(global_camera==nullptr);global_camera=this;}virtual void setup(){};virtual float get_setup_priority()const{return 0;}
 virtual void add_listener(CameraListener*)=0;virtual CameraImageReader *create_image_reader()=0;virtual void request_image(CameraRequester)=0;virtual void start_stream(CameraRequester)=0;virtual void stop_stream(CameraRequester)=0;
 static Camera *instance(){return global_camera;}virtual void loop(){}protected:inline static Camera *global_camera=nullptr;
};
}
namespace esp32_camera {
struct FB{struct timeval timestamp{7,0};};
struct ESP32CameraImage:camera::CameraImage{FB fb;uint8_t data[4]={255,216,255,217};FB *get_raw_buffer(){return &fb;}uint8_t *get_data_buffer()override{return data;}size_t get_data_length()override{return 4;}bool was_requested_by(camera::CameraRequester r)const override{return r==camera::API_REQUESTER;}};
struct ESP32Camera:camera::Camera{
 std::vector<camera::CameraListener*> listeners;int requests=0,starts=0,stops=0;
 void add_listener(camera::CameraListener *l)override{listeners.push_back(l);}camera::CameraImageReader *create_image_reader()override{return nullptr;}
 void request_image(camera::CameraRequester)override{++requests;}void start_stream(camera::CameraRequester)override{++starts;for(auto *l:listeners)l->on_stream_start();}void stop_stream(camera::CameraRequester)override{++stops;for(auto *l:listeners)l->on_stream_stop();}
};
}
}
std::vector<uint8_t> rendered;bool encoder_fail=false;int encodes=0;
extern "C" {
jpeg_error_t jpeg_dec_open(jpeg_dec_config_t*,jpeg_dec_handle_t *h){*h=reinterpret_cast<void*>(1);return JPEG_ERR_OK;}
jpeg_error_t jpeg_dec_parse_header(jpeg_dec_handle_t,jpeg_dec_io_t*,jpeg_dec_header_info_t *h){h->width=640;h->height=480;return JPEG_ERR_OK;}
jpeg_error_t jpeg_dec_process(jpeg_dec_handle_t,jpeg_dec_io_t *io){memset(io->outbuf,77,640*480*3);return JPEG_ERR_OK;}
jpeg_error_t jpeg_dec_close(jpeg_dec_handle_t){return JPEG_ERR_OK;}
jpeg_error_t jpeg_enc_open(jpeg_enc_config_t *c,jpeg_enc_handle_t *h){assert(c->width==640&&c->height==480&&c->quality==85&&c->src_type==JPEG_PIXEL_FORMAT_RGB888);*h=reinterpret_cast<void*>(1);return JPEG_ERR_OK;}
jpeg_error_t jpeg_enc_process(jpeg_enc_handle_t,const uint8_t *in,int n,uint8_t *out,int capacity,int *len){++encodes;assert(capacity>=32);rendered.assign(in,in+n);if(encoder_fail)return JPEG_ERR_FAIL;memset(out,123,32);out[0]=255;out[1]=216;*len=32;return JPEG_ERR_OK;}
jpeg_error_t jpeg_enc_close(jpeg_enc_handle_t){return JPEG_ERR_OK;}
}
'''+f'#include "{root/"components/meter_setup/timestamp_overlay.h"}"\n'+body+r'''
using namespace esphome;using namespace esphome::meter_setup;
struct Listener:camera::CameraListener{std::shared_ptr<camera::CameraImage> last;int starts=0,stops=0;void on_camera_image(const std::shared_ptr<camera::CameraImage> &p)override{last=p;}void on_stream_start()override{++starts;}void on_stream_stop()override{++stops;}};
int main(){
 setenv("TZ","Europe/Berlin",1);tzset();
 std::vector<uint8_t> expected(640*480*3,77);assert(draw_capture_timestamp(expected.data(),expected.size(),640,480,"12.10.2026 13:45:39"));
 auto raw=std::make_shared<esp32_camera::ESP32CameraImage>();
 struct tm local{};local.tm_year=126;local.tm_mon=9;local.tm_mday=12;local.tm_hour=13;local.tm_min=45;local.tm_sec=39;local.tm_isdst=-1;const auto captured=mktime(&local);
 auto jpeg=timestamp_jpeg(raw->data,4,captured);assert(jpeg.size==32&&rendered==expected&&raw->data[0]==255&&raw->data[1]==216&&raw->data[2]==255);
 for(int y=0;y<480;y++)for(int x=0;x<640;x++)if(y<456||y>=478||x<4||x>=240)assert(rendered[(y*640+x)*3]==77);
 assert(!draw_capture_timestamp(expected.data(),2,640,480,"12.10.2026 13:45:39"));
 assert(!draw_capture_timestamp(expected.data(),expected.size(),640,480,"wrong"));
 timestamp_jpeg(raw->data,4,0);expected.assign(640*480*3,77);draw_capture_timestamp(expected.data(),expected.size(),640,480,"--.--.---- --:--:--");assert(rendered==expected);
 const auto now=time(nullptr);assert(std::abs(camera_capture_epoch(raw)-(now-3))<=1);
 esp32_camera::ESP32Camera physical;physical.name="Wasserzähler Kamera";physical.hash=123456;
 Listener ocr,api;physical.add_listener(&ocr);auto *proxy=TimestampCamera::install(&physical);proxy->setup();proxy->add_listener(&api);
 assert(camera::Camera::instance()==proxy&&proxy->name==physical.name&&proxy->hash==physical.hash);
 for(auto *l:physical.listeners)l->on_camera_image(raw);assert(ocr.last==raw&&api.last!=raw&&api.last->get_data_length()==32&&api.last->was_requested_by(camera::API_REQUESTER));
 auto reader=std::unique_ptr<camera::CameraImageReader>(proxy->create_image_reader());reader->set_image(api.last);assert(reader->available()==32&&reader->peek_data_buffer()[0]==255);reader->consume_data(12);assert(reader->available()==20);reader->consume_data(100);assert(reader->available()==0);reader->return_image();assert(reader->peek_data_buffer()==nullptr);
 proxy->request_image(camera::API_REQUESTER);proxy->loop();assert(physical.requests==0);proxy->start_stream(camera::API_REQUESTER);proxy->loop();proxy->stop_stream(camera::API_REQUESTER);assert(physical.requests==0&&physical.starts==1&&physical.stops==1&&api.starts==1&&api.stops==1);
 encoder_fail=true;proxy->on_camera_image(raw);assert(api.last==raw&&ocr.last==raw);
 CameraPowerController power;proxy->set_power(&power);auto held=api.last;proxy->request_image(camera::API_REQUESTER);proxy->loop();assert(physical.requests==0&&power.requests==0); // cached still polls never wake the sensor
 power.awake=false;proxy->start_stream(camera::API_REQUESTER);proxy->loop();assert(physical.starts==1&&power.requests==1);power.awake=true;proxy->loop();assert(physical.starts==2&&power.requests==2);proxy->stop_stream(camera::API_REQUESTER);assert(physical.stops==2);
 delete proxy;
 std::cout<<"Timestamp camera passed: German capture time, bounded overlay, untouched OCR source, unsynchronized clock, camera identity, API reader lifetime, stream forwarding and codec failure fallback\n";
}
'''
include=root/'.esphome/build/wasserzaehler/managed_components/espressif__esp_new_jpeg/include'
with tempfile.TemporaryDirectory(prefix='meter-timestamp-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-I',str(include),'-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
