"""Exercise the actual reader interception and fail-closed flow with host camera fakes."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
header=(root/'components/meter_setup/meter_setup.h').read_text()
settings=header[header.index('struct Settings {'):header.index('class MeterSetup')]
processing=cpp[cpp.index('static ImageBuffer grayscale('):cpp.index('bool MeterSetup::save_configuration_(')]
source=r'''
#include <memory>
#include <mutex>
#include <atomic>
#include <string>
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <random>
#define MALLOC_CAP_SPIRAM 0
#define MALLOC_CAP_8BIT 0
#define ESP_LOGW(...)
#define ESP_LOGI(...)
void *heap_caps_malloc(size_t n,int){return malloc(n);}
void heap_caps_free(void *p){free(p);}
uint32_t millis(){static uint32_t tick=0;return ++tick;}
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\n'+r'''
namespace esphome::meter_setup {
namespace camera {
enum CameraRequester {IDLE,API_REQUESTER,WEB_REQUESTER};
class CameraImage {public:virtual ~CameraImage(){};virtual uint8_t *get_data_buffer()=0;virtual size_t get_data_length()=0;virtual bool was_requested_by(CameraRequester)const=0;};
}
namespace meter_reader_tflite {
class MeterReaderTFLite {
 public:
 enum class FrameState {IDLE,REQUESTED,AVAILABLE};
 std::atomic<FrameState> frame_state_{FrameState::REQUESTED};std::mutex frame_mutex_;
 std::shared_ptr<camera::CameraImage> pending_frame_;int calls=0;bool paused=false;std::string crops;
 virtual void on_camera_image(const std::shared_ptr<camera::CameraImage>& image){++calls;pending_frame_=image;frame_state_=FrameState::AVAILABLE;}
 void set_pause_processing(bool p){paused=p;}void set_crop_zones(const std::string &s){crops=s;}
};
}
'''+settings+r'''
class MeterSetup {
 public:
 std::mutex mutex_;bool busy_=true,test_=false,accepted_=true;uint32_t next_=0,alignment_ms_=0;
 Settings settings_{},pending_{};AlignmentReference active_alignment_{};AlignmentMatch alignment_matches_[2]{};
 std::string alignment_result_,message_,reading_error_;bool reading_problem_=false;
 meter_reader_tflite::MeterReaderTFLite *reader_{};
 std::shared_ptr<uint8_t> preview_;size_t preview_size_=0;uint32_t preview_sequence_=0;bool preview_rgb_=false;
 void set_preview_(const std::shared_ptr<uint8_t>&v,size_t n,bool rgb){preview_=v;preview_size_=n;preview_rgb_=rgb;}
 bool accepts_reader_frame_(){return busy_;}
 void set_illumination_(bool,const IlluminationSettings&){}
 bool inference_started_=true,light_test_=false;IlluminationSettings pending_illumination_{};
 std::shared_ptr<camera::CameraImage> align_image_(const std::shared_ptr<camera::CameraImage>& image);
};
class AlignedMeterReader:public meter_reader_tflite::MeterReaderTFLite {
 public:MeterSetup *owner_{};void on_camera_image(const std::shared_ptr<camera::CameraImage>& image)override;
};
std::string zones(const Settings&){return "saved crops";}
using ImageBuffer=std::shared_ptr<uint8_t>;
int decode_count=0;
ImageBuffer decode_rgb(const uint8_t *data,size_t size){++decode_count;if(size!=640*480*3)return {};auto p=ImageBuffer(static_cast<uint8_t*>(malloc(size)),free);memcpy(p.get(),data,size);return p;}
'''+processing+r'''
class FakeImage:public camera::CameraImage {
 public:std::vector<uint8_t> pixels;FakeImage():pixels(640*480*3,100){}
 uint8_t *get_data_buffer()override{return pixels.data();}size_t get_data_length()override{return pixels.size();}
 bool was_requested_by(camera::CameraRequester r)const override{return r==camera::WEB_REQUESTER;}
};
}
int main(){
 using namespace esphome::meter_setup;
 MeterSetup owner;AlignedMeterReader reader;owner.reader_=&reader;reader.owner_=&owner;owner.settings_.baseline=1864266;
 auto image=std::make_shared<FakeImage>();reader.on_camera_image(image);
 assert(reader.calls==1&&reader.pending_frame_==image&&decode_count==0); // Disabled path preserves image identity and cost.
 owner.active_alignment_.enabled=owner.active_alignment_.ready=1;
 uint16_t regions[2][4]={{120,210,152,242},{480,210,512,242}};memcpy(owner.active_alignment_.regions,regions,sizeof(regions));
 owner.test_=true;owner.settings_.calibrated=1;reader.frame_state_=meter_reader_tflite::MeterReaderTFLite::FrameState::REQUESTED;reader.on_camera_image(image);
 assert(!owner.preview_);assert(reader.calls==1&&!reader.pending_frame_&&!owner.busy_&&!owner.accepted_&&reader.paused);
 assert(owner.settings_.baseline==1864266&&!owner.reading_problem_&&reader.crops=="saved crops"); // Test failure restores saved crops and isolates HA.
 owner.test_=false;owner.busy_=true;reader.frame_state_=meter_reader_tflite::MeterReaderTFLite::FrameState::REQUESTED;reader.on_camera_image(image);
 assert(reader.calls==1&&owner.reading_problem_&&owner.reading_error_.find("Ausrichtungsfehler")!=std::string::npos&&owner.settings_.baseline==1864266);
 std::vector<uint8_t> gray(640*480);std::mt19937 random(321);
 for(size_t i=0;i<gray.size();i++){gray[i]=random()%200+20;image->pixels[i*3]=image->pixels[i*3+1]=image->pixels[i*3+2]=gray[i];}
 assert(capture_reference(gray.data(),owner.active_alignment_));
 for(int i=0;i<8;i++){auto &b=owner.settings_.boxes[i];b[0]=100+i*40;b[1]=100;b[2]=130+i*40;b[3]=150;}
 owner.busy_=true;reader.frame_state_=meter_reader_tflite::MeterReaderTFLite::FrameState::REQUESTED;reader.on_camera_image(image);
 assert(reader.calls==2&&reader.pending_frame_!=image&&reader.pending_frame_->get_data_length()==640*480*3&&owner.alignment_result_=="OK");
 assert(owner.preview_rgb_&&owner.preview_size_==640*480*3&&owner.preview_.get()==reader.pending_frame_->get_data_buffer());
 assert(reader.pending_frame_->was_requested_by(camera::WEB_REQUESTER)&&!reader.pending_frame_->was_requested_by(camera::API_REQUESTER));
 assert(memcmp(reader.pending_frame_->get_data_buffer(),image->pixels.data(),image->pixels.size())==0); // Same corrected frame reaches the reader.
 std::cout<<"Alignment flow passed: zero-cost disabled path, no inference on failure, crop restore, unchanged baseline, HA error, same-image successful handoff\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-alignment-flow-') as temp:
 binary=str(Path(temp)/'flow')
 subprocess.run(['g++','-std=c++17','-O2','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
