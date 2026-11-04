/* SPDX-License-Identifier: MIT */
/* Only authored register/clock peers; no hardware or notification transport. */
#include "ShengDpuObservation.h"
#include "ShengDpuSourceFacts.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static uint32_t mdss[SourceMdssBytes/4],mdp[SourceMdpBytes/4];
static struct {
    unsigned reads,fail_at,clock_calls,clock_backwards;
    unsigned mutate_region,mutate_occurrence,mutate_reads,mutate_once;
    size_t mutate_offset;
    uint32_t mutate_xor;
    unsigned last_region;size_t last_offset;
} f;
static int allowed(unsigned region,size_t offset) {
    if(region==ShengDpuMdssRegion)return offset==SourceHwVersion || offset==SourceMdssIrq;
    if(region!=ShengDpuMdpRegion)return 0;
    if(offset==SourceHwVersion || offset==SourceIrqEnable || offset==SourceIrqStatus)return 1;
    for(unsigned i=0;i<2;++i)for(size_t j=0;j<sizeof SourceIntfOffsets/sizeof *SourceIntfOffsets;++j)
        if(offset==SourceIntfBase[i]+SourceIntfOffsets[j])return 1;
    return 0;
}
static int read32(void *cookie,unsigned region,size_t offset,uint32_t *out) {
    CHECK(cookie==&f && out && allowed(region,offset));
    ++f.reads;f.last_region=region;f.last_offset=offset;
    if(f.reads==f.fail_at)return 1;
    uint32_t *words=region==ShengDpuMdssRegion?mdss:mdp;
    if(f.mutate_xor && region==f.mutate_region && offset==f.mutate_offset) {
        ++f.mutate_reads;
        if(!f.mutate_once || f.mutate_reads==f.mutate_occurrence)words[offset/4]^=f.mutate_xor;
    }
    *out=words[offset/4];return 0;
}
static uint64_t now_ns(void *cookie) {
    CHECK(cookie==&f);++f.clock_calls;
    return f.clock_backwards?1000-f.clock_calls:1000+f.clock_calls;
}
static ShengDpuObservationIo io;
static void reset(void) {
    memset(&f,0,sizeof f);memset(mdss,0,sizeof mdss);memset(mdp,0,sizeof mdp);
    io=(ShengDpuObservationIo){&f,{SourceMdssBytes,SourceMdpBytes},read32,now_ns};
    mdss[SourceHwVersion/4]=0x90000000;mdss[SourceMdssIrq/4]=1;
    mdp[SourceHwVersion/4]=0x90000001;
    mdp[SourceIrqEnable/4]=(1u<<SourceVsyncBits[0])|2;
    mdp[SourceIrqStatus/4]=(1u<<SourceVsyncBits[0])|(1u<<SourceVsyncBits[1]);
    for(unsigned i=0;i<2;++i) {
        size_t b=SourceIntfBase[i];mdp[(b+SourceStatus)/4]=1;
        mdp[(b+SourceTimingEnable)/4]=1;mdp[(b+SourceCountEnable)/4]=3;
        mdp[(b+SourceFrame)/4]=100+i;mdp[(b+SourceLine)/4]=42;
        mdp[(b+SourceHsync)/4]=0x12340056;mdp[(b+SourceVperiod)/4]=0x789abc;
    }
}
static void empty(const ShengDpuObservation *s) {
    const unsigned char *p=(const unsigned char *)s;for(size_t i=0;i<sizeof *s;++i)CHECK(!p[i]);
}
int main(void) {
    ShengDpuObservation s;ShengDpuObservationResult r;
    reset();CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationComplete);
    CHECK(r.attempts==1 && r.reads==42 && f.reads==42 && f.clock_calls==2);
    CHECK(s.active_mask==3 && s.counters_enabled_mask==3 && !s.command_trigger_mask);
    CHECK(s.vsync_enabled_mask==1 && s.vsync_pending_mask==3 && s.began_ns<=s.ended_ns);
    CHECK(s.interfaces[0].frame==100 && s.interfaces[1].frame==101);
    /* Inactive/disabled/unknown versions remain raw observations, never readiness. */
    reset();mdp[(SourceIntfBase[0]+SourceStatus)/4]=0;
    mdp[(SourceIntfBase[1]+SourceCountEnable)/4]=0;
    mdp[(SourceIntfBase[0]+SourceCommandTrigger)/4]=1;mdp[0]=0;
    CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationComplete);
    CHECK(s.active_mask==2 && s.counters_enabled_mask==1 && s.command_trigger_mask==1 && s.mdp_version==0);
    for(unsigned bad=0;bad<8;++bad) {
        reset();ShengDpuObservationIo test=io;
        if(bad==0)test.read32=0;if(bad==1)test.now_ns=0;
        if(bad==2)test.region_bytes[0]=SourceMdssBytes-1;
        if(bad==3)test.region_bytes[1]=SourceMdpBytes-1;
        CHECK(ShengDpuObserve(bad==4?0:&test,bad==5?0:&s,bad==6?0:&r)==(bad==7?ShengDpuObservationComplete:ShengDpuObservationArgument));
        if(bad!=7)CHECK(!f.reads);
    }
    for(unsigned failed=1;failed<=42;++failed) {
        reset();f.fail_at=failed;memset(&s,0xa5,sizeof s);
        CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationIoError);
        CHECK(r.reads==failed && r.failed_region==f.last_region && r.failed_offset==f.last_offset);empty(&s);
    }
    /* Mode, counter and enable changes cannot publish a mixed snapshot. */
    const size_t unstable[]={SourceHwVersion,SourceIrqEnable,SourceIntfBase[0]+SourceStatus,
        SourceIntfBase[0]+SourceTimingEnable,SourceIntfBase[0]+SourceCountEnable,SourceIntfBase[0]+SourceCommandTrigger,
        SourceIntfBase[0]+SourceFrame,SourceIntfBase[0]+SourceHsync,SourceIntfBase[0]+SourceVperiod};
    for(size_t i=0;i<sizeof unstable/sizeof *unstable;++i) {
        reset();f.mutate_region=ShengDpuMdpRegion;f.mutate_offset=unstable[i];f.mutate_xor=1;
        CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationUnstable);
        CHECK(r.attempts==3 && r.reads==126);empty(&s);
    }
    reset();f.mutate_region=ShengDpuMdpRegion;f.mutate_offset=SourceIntfBase[0]+SourceFrame;
    f.mutate_xor=1;f.mutate_once=1;f.mutate_occurrence=2;
    CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationComplete && r.attempts==2 && r.reads==84);
    reset();mdp[(SourceIntfBase[0]+SourceFrame)/4]=UINT32_MAX;
    f.mutate_region=ShengDpuMdpRegion;f.mutate_offset=SourceIntfBase[0]+SourceFrame;
    f.mutate_xor=UINT32_MAX;f.mutate_once=1;f.mutate_occurrence=2;
    CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationComplete && r.attempts==2 && !s.interfaces[0].frame);
    reset();f.mutate_region=ShengDpuMdpRegion;f.mutate_offset=SourceIntfBase[0]+SourceFrame;f.mutate_xor=1;f.fail_at=80;
    CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationIoError && r.attempts==2 && r.reads==80);empty(&s);
    /* Natural line/IRQ/unknown status-bit changes do not fake a mode change. */
    const size_t natural[]={SourceIrqStatus,SourceIntfBase[0]+SourceLine,SourceIntfBase[0]+SourceStatus};
    for(unsigned i=0;i<3;++i) {
        reset();f.mutate_region=ShengDpuMdpRegion;f.mutate_offset=natural[i];f.mutate_xor=i==2?128:1;
        CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationComplete && r.attempts==1);
    }
    reset();f.clock_backwards=1;
    CHECK(ShengDpuObserve(&io,&s,&r)==ShengDpuObservationClockError);empty(&s);
    puts("PASS: source-bound DPU observation: stable/inactive/raw version, 7 argument refusals, 42 read faults, 9 unstable fields, retry/wrap/late failure, natural changes and clock reversal; software peer only, no VBL or hardware access");
}
