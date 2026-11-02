//
// Copyright(C) 1993-1996 Id Software, Inc.
// Copyright(C) 2005-2014 Simon Howard
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// DESCRIPTION:
//	Archiving: SaveGame I/O.
//	Thinker, Ticker.
//


#include <stdio.h>
#include <stdlib.h>

#include "z_zone.h"
#include "p_local.h"

#include "doomstat.h"
#include "d_loop.h"
#include "r_state.h"


int	leveltime;

//
// THINKERS
// All thinkers should be allocated by Z_Malloc
// so they can be operated on uniformly.
// The actual structures will vary in size,
// but the first element must be thinker_t.
//



// Both the head and tail of the thinker list.
thinker_t	thinkercap;


//
// P_InitThinkers
//
void P_InitThinkers (void)
{
    thinkercap.prev = thinkercap.next  = &thinkercap;
}




//
// P_AddThinker
// Adds a new thinker at the end of the list.
//
void P_AddThinker (thinker_t* thinker)
{
    thinkercap.prev->next = thinker;
    thinker->next = &thinkercap;
    thinker->prev = thinkercap.prev;
    thinkercap.prev = thinker;
}



//
// P_RemoveThinker
// Deallocation is lazy -- it will not actually be freed
// until its thinking turn comes up.
//
void P_RemoveThinker (thinker_t* thinker)
{
  // FIXME: NOP.
  thinker->function.acv = (actionf_v)(-1);
}



//
// P_AllocateThinker
// Allocates memory and adds a new thinker at the end of the list.
//
void P_AllocateThinker (thinker_t*	thinker)
{
}



//
// P_RunThinkers
//
void P_RunThinkers (void)
{
    thinker_t*	currentthinker;

    currentthinker = thinkercap.next;
    while (currentthinker != &thinkercap)
    {
	if ( currentthinker->function.acv == (actionf_v)(-1) )
	{
	    // time to remove it
	    currentthinker->next->prev = currentthinker->prev;
	    currentthinker->prev->next = currentthinker->next;
	    Z_Free (currentthinker);
	}
	else
	{
	    if (currentthinker->function.acp1)
		currentthinker->function.acp1 (currentthinker);
	}
	currentthinker = currentthinker->next;
    }
}



//
// P_Ticker
//

// FNV-1a: fold one int into a running hash
static unsigned int fnv(unsigned int h, int v)
{
    unsigned char *b = (unsigned char *) &v;
    int k;
    for (k = 0; k < 4; k++)
    {
        h ^= b[k];
        h *= 16777619u;
    }
    return h;
}

void P_Ticker (void)
{
    int		i;
    
    // run the tic
    if (paused)
	return;

    // NUDGE_TIC=N: one extra gameplay dice roll at tic N (butterfly experiment)
    {
        static int nudge_tic = -2;
        extern int prndindex;
        if (nudge_tic == -2)
        {
            const char *s = getenv("NUDGE_TIC");
            nudge_tic = s ? atoi(s) : -1;
        }
        if (gametic == nudge_tic)
            prndindex = (prndindex + 1) & 0xff;
    }
		
    // pause if in menu and at least one tic has been run
    if ( !netgame
	 && menuactive
	 && !demoplayback
	 && players[consoleplayer].viewz != 1)
    {
	return;
    }
    
		
    for (i=0 ; i<MAXPLAYERS ; i++)
	if (playeringame[i])
	    P_PlayerThink (&players[i]);
			
    P_RunThinkers ();
    P_UpdateSpecials ();
    P_RespawnSpecials ();

    // for par times
    leveltime++;	

    // STATELOG=path: per tic "tic x y angle health worldhash"
    {
        static FILE *st_log = NULL;
        if (!st_log && getenv("STATELOG"))
        {
            st_log = fopen(getenv("STATELOG"), "w");
            if (st_log) setvbuf(st_log, NULL, _IOLBF, 0);
        }
        if (st_log && players[consoleplayer].mo)
        {
            mobj_t *m = players[consoleplayer].mo;
            unsigned int wh = 2166136261u;
            thinker_t *th;
            int s;

            for (th = thinkercap.next; th != &thinkercap; th = th->next)
            {
                if (th->function.acp1 == (actionf_p1) P_MobjThinker)
                {
                    mobj_t *mo = (mobj_t *) th;
                    wh = fnv(wh, mo->type);
                    wh = fnv(wh, mo->x);
                    wh = fnv(wh, mo->y);
                    wh = fnv(wh, mo->z);
                    wh = fnv(wh, mo->health);
                    wh = fnv(wh, mo->tics);
                }
            }
            for (s = 0; s < numsectors; s++)
            {
                wh = fnv(wh, sectors[s].floorheight);
                wh = fnv(wh, sectors[s].ceilingheight);
            }
            fprintf(st_log, "%d %d %d %d %d %u\n", gametic,
                    m->x, m->y, (int)m->angle, players[consoleplayer].health, wh);
        }
    }
}
