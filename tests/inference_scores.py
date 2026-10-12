"""Exercise production score extraction before the upstream queue consumer."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
src=(root/'components/meter_setup/features.cpp').read_text()
loop=src[src.index('void AlignedMeterReader::loop()'):src.index('void MeterSetup::features_loop_()')]
source=r'''
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
#include <iostream>
#define SUPPORT_DOUBLE_BUFFERING
#define pdTRUE 1
struct Result {std::vector<float> readings,probabilities;};
struct Queue {Result *result=nullptr;};
int xQueuePeek(Queue *q,Result **r,int){*r=q->result;return *r!=nullptr;}
struct MeterSetup {std::string digits;float values[8]{};int captures=0;
 void capture_digit_scores_(const std::string &s,const float *v){digits=s;for(int i=0;i<8;i++)values[i]=v[i];++captures;}
};
struct MeterReaderTFLite {using InferenceResult=Result;Queue *output_queue_=nullptr;int consumed=0;
 void loop(){if(output_queue_&&output_queue_->result){output_queue_->result=nullptr;++consumed;}}
};
struct AlignedMeterReader:MeterReaderTFLite{MeterSetup *owner_=nullptr;void loop();};
'''+loop+r'''
int main(){
 Result r{{0,1,8,6,4,2,6,6},{.996f,.957f,.996f,.996f,.867f,.973f,.988f,.957f}};
 Queue q{&r};MeterSetup owner;AlignedMeterReader reader;reader.owner_=&owner;reader.output_queue_=&q;
 reader.loop();assert(owner.captures==1&&owner.digits=="01864266"&&reader.consumed==1&&q.result==nullptr);
 const float expected[]={99.6f,95.7f,99.6f,99.6f,86.7f,97.3f,98.8f,95.7f};for(int i=0;i<8;i++)assert(std::abs(owner.values[i]-expected[i])<.001f);
 reader.loop();assert(owner.captures==1);
 r.readings[7]=9.8f;q.result=&r;reader.loop();assert(owner.digits=="01864260");
 r.probabilities[0]=NAN;q.result=&r;reader.loop();assert(owner.captures==2&&reader.consumed==3);
 r.probabilities.pop_back();q.result=&r;reader.loop();assert(owner.captures==2&&reader.consumed==4);
 std::cout<<"Inference score tests passed: exact eight scores, digit rollover, single-consumer ownership, invalid/short results\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-scores-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
