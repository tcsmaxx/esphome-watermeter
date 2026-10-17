"""Exercise the production preview encoder and deferred preparation with codec/heap failures."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/preview_jpeg.cpp').read_text().split('namespace esphome::meter_setup {',1)[1]
source=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>
#include <iostream>
#define ESP_LOGW(...)
constexpr int MALLOC_CAP_SPIRAM=1,MALLOC_CAP_8BIT=2,JPEG_PIXEL_FORMAT_RGB888=3,JPEG_SUBSAMPLE_444=4,JPEG_ERR_OK=0;
struct jpeg_enc_config_t{int width,height,src_type,quality,subsampling;};
#define DEFAULT_JPEG_ENC_CONFIG() jpeg_enc_config_t{}
using jpeg_enc_handle_t=void*;
int failure=0,opens=0,closes=0,encodes=0;
int jpeg_enc_open(jpeg_enc_config_t*c,void**p){assert(c->width==640&&c->height==480&&c->quality==95&&c->subsampling==JPEG_SUBSAMPLE_444&&c->src_type==JPEG_PIXEL_FORMAT_RGB888);opens++;*p=(void*)1;return failure==1?-1:0;}
int jpeg_enc_process(void*,uint8_t*in,size_t n,uint8_t*out,size_t cap,int*len){encodes++;assert(n==640*480*3&&cap==384*1024&&in[0]==77);if(failure==3)return -1;out[0]=0xff;out[1]=0xd8;*len=100;return 0;}
void jpeg_enc_close(void*){closes++;}
void*heap_caps_aligned_alloc(size_t a,size_t n,int){return failure==2?nullptr:aligned_alloc(a,n);}
void*heap_caps_malloc(size_t n,int){return failure==4?nullptr:malloc(n);}
void heap_caps_free(void*p){free(p);}
namespace esphome::meter_setup {
struct PreviewJpeg{std::shared_ptr<uint8_t>data;size_t size=0;};
struct MeterSetup{std::shared_ptr<uint8_t>preview_,preview_jpeg_;size_t preview_size_=0,preview_jpeg_size_=0;uint32_t preview_sequence_=7,preview_jpeg_sequence_=0;bool preview_rgb_=true,preview_encode_pending_=true,preview_encode_failed_=false;void prepare_preview_();};
'''+cpp+r'''
int main(){using namespace esphome::meter_setup;std::vector<uint8_t>rgb(640*480*3,77);
assert(!encode_preview_jpeg(nullptr,rgb.size()).data);assert(!encode_preview_jpeg(rgb.data(),10).data);assert(opens==0);
for(failure=0;failure<5;failure++){int before=closes;auto result=encode_preview_jpeg(rgb.data(),rgb.size());assert(bool(result.data)==(failure==0||failure==4));if(result.data)assert(result.size==100&&result.data.get()[0]==0xff);assert(closes-before==(failure==1?0:1));assert(rgb.front()==77&&rgb.back()==77);}
failure=0;MeterSetup m;m.preview_=std::shared_ptr<uint8_t>(rgb.data(),[](uint8_t*){});m.preview_size_=rgb.size();m.prepare_preview_();assert(!m.preview_encode_pending_&&!m.preview_encode_failed_&&m.preview_jpeg_size_==100&&m.preview_jpeg_sequence_==7);
failure=3;m.preview_encode_pending_=true;m.prepare_preview_();assert(!m.preview_encode_pending_&&m.preview_encode_failed_&&!m.preview_jpeg_);
std::cout<<"Preview encoder passed: RGB unchanged, JPEG config, deferred preparation, codec/allocation failures and compact-buffer fallback\n";
}
'''
with tempfile.TemporaryDirectory() as tmp:
 binary=str(Path(tmp)/'preview')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
