/* SPDX-License-Identifier: MIT */
#include "ShengDpuObservation.h"
#include <string.h>
/* Register facts from the pinned source manifest in sheng-display-inputs.json.
 * No original/vendor implementation is copied. Physical resources are bound by
 * the platform, not guessed here. Offsets are relative to each named region. */
enum {MdssBytes=0x1000,MdpBytes=0x8f000,Dsi0IntfBase=0x35000,DsiIntfStride=0x1000};
static int read_reg(const ShengDpuObservationIo *io,unsigned region,size_t offset,uint32_t *out,ShengDpuObservationResult *r)
{
    ++r->reads;
    if((offset&3) || offset>io->region_bytes[region] || 4>io->region_bytes[region]-offset ||
       io->read32(io->cookie,region,offset,out)) {
        r->failed_region=region;r->failed_offset=offset;return 1;
    }
    return 0;
}
static int sample(const ShengDpuObservationIo *io,ShengDpuObservation *s,ShengDpuObservationResult *r)
{
    if(read_reg(io,ShengDpuMdpRegion,0,&s->mdp_version,r) ||
       read_reg(io,ShengDpuMdssRegion,0,&s->mdss_version,r) ||
       read_reg(io,ShengDpuMdssRegion,0x10,&s->mdss_irq_status,r) ||
       read_reg(io,ShengDpuMdpRegion,0x10,&s->mdp_irq_enable,r) ||
       read_reg(io,ShengDpuMdpRegion,0x14,&s->mdp_irq_status,r))return 1;
    for(unsigned i=0;i<2;++i) {
        const size_t base=Dsi0IntfBase+i*DsiIntfStride;
        ShengDpuInterfaceObservation *v=&s->interfaces[i];
        if(read_reg(io,ShengDpuMdpRegion,base+0x26c,&v->status,r) ||
           read_reg(io,ShengDpuMdpRegion,base,&v->timing_enable,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0xa8,&v->count_enable,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0x84,&v->command_trigger,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0xac,&v->frame,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0xb0,&v->line,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0x08,&v->hsync,r) ||
           read_reg(io,ShengDpuMdpRegion,base+0x0c,&v->vsync_period,r))return 1;
    }
    return 0;
}
static int same(const ShengDpuObservation *a,const ShengDpuObservation *b)
{
    if(a->mdp_version!=b->mdp_version || a->mdss_version!=b->mdss_version || a->mdp_irq_enable!=b->mdp_irq_enable)return 0;
    for(unsigned i=0;i<2;++i) {
        const ShengDpuInterfaceObservation *x=&a->interfaces[i],*y=&b->interfaces[i];
        /* Only the source-defined active bit is interpreted in INTF_STATUS.
         * Line counters and pending IRQ bits can naturally change between reads. */
        if(((x->status^y->status)&1) || x->timing_enable!=y->timing_enable || x->count_enable!=y->count_enable ||
           x->command_trigger!=y->command_trigger || x->frame!=y->frame || x->hsync!=y->hsync || x->vsync_period!=y->vsync_period)return 0;
    }
    return 1;
}
ShengDpuObservationStatus ShengDpuObserve(const ShengDpuObservationIo *io,ShengDpuObservation *out,ShengDpuObservationResult *r)
{
    if(out)memset(out,0,sizeof *out);if(r)memset(r,0,sizeof *r);
    if(!io || !out || !r || !io->read32 || !io->now_ns || io->region_bytes[0]<MdssBytes || io->region_bytes[1]<MdpBytes)
        return ShengDpuObservationArgument;
    for(unsigned attempt=1;attempt<=ShengDpuObservationMaxAttempts;++attempt) {
        r->attempts=attempt;
        ShengDpuObservation a,b;memset(&a,0,sizeof a);memset(&b,0,sizeof b);
        uint64_t began=io->now_ns(io->cookie);
        if(sample(io,&a,r) || sample(io,&b,r))return ShengDpuObservationIoError;
        uint64_t ended=io->now_ns(io->cookie);
        if(ended<began)return ShengDpuObservationClockError;
        if(!same(&a,&b))continue;
        b.began_ns=began;b.ended_ns=ended;
        for(unsigned i=0;i<2;++i) {
            const ShengDpuInterfaceObservation *v=&b.interfaces[i];
            if(v->status&1)b.active_mask|=1u<<i;
            if((v->count_enable&3)==3)b.counters_enabled_mask|=1u<<i;
            if(v->command_trigger)b.command_trigger_mask|=1u<<i;
            /* DPU catalog: top0 group bits 27/29, not DSI controller IRQs. */
            const uint32_t bit=UINT32_C(1)<<(27+2*i);
            if(b.mdp_irq_enable&bit)b.vsync_enabled_mask|=1u<<i;
            if(b.mdp_irq_status&bit)b.vsync_pending_mask|=1u<<i;
        }
        memcpy(out,&b,sizeof b);return ShengDpuObservationComplete;
    }
    return ShengDpuObservationUnstable;
}
