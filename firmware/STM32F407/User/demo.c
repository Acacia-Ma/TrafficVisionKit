/**
 * @file  demo.c
 * @brief ATK-MC5640 JPEG -> MO395Q UDP -> PC (bare-metal, no FreeRTOS)
 *
 * UDP packet format (matches udp_jpeg_receiver.py):
 *   Byte  0-1  : Magic 0xA5 0x5A
 *   Byte  2-5  : frame_id  (uint32 LE)
 *   Byte  6-7  : chunk_idx (uint16 LE)
 *   Byte  8-9  : chunk_cnt (uint16 LE)
 *   Byte 10-13 : jpeg_len  (uint32 LE)
 *   Byte 14-15 : payload_len (uint16 LE)
 *   Byte 16+   : JPEG payload
 */

#include "demo.h"
#include "./BSP/ATK_MC5640/atk_mc5640.h"
#include "./BSP/ATK_MO395Q/atk_mo395q.h"
#include "./BSP/ATK_MO395Q/atk_mo395q_cmd.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/LED/led.h"
#include <string.h>
#include <stdint.h>

/* ---------- Network config ---------- */
#define DEMO_LOCAL_IP_1     192
#define DEMO_LOCAL_IP_2     168
#define DEMO_LOCAL_IP_3     100
#define DEMO_LOCAL_IP_4     100

#define DEMO_GW_1           192
#define DEMO_GW_2           168
#define DEMO_GW_3           100
#define DEMO_GW_4           1

#define DEMO_MASK_1         255
#define DEMO_MASK_2         255
#define DEMO_MASK_3         255
#define DEMO_MASK_4         0

#define DEMO_PC_IP_1        192
#define DEMO_PC_IP_2        168
#define DEMO_PC_IP_3        100
#define DEMO_PC_IP_4        50
#define DEMO_PC_PORT        8080
#define DEMO_LOCAL_PORT     50000

/* ---------- Camera config ---------- */
#define DEMO_CAM_WIDTH      320
#define DEMO_CAM_HEIGHT     240

/*
 * Buffer must be >= JPEG output size. For 320x240 JPEG the actual size is
 * 10-20 KB, but DMA transfer count is set to width*height/4 = 19200 words
 * (76800 bytes) by the driver. In SNAPSHOT+DMA_CIRCULAR mode, DMA stops at
 * VSYNC so actual bytes written == JPEG size (not 76800). 40 KB gives safe
 * headroom without waste.
 */
#define DEMO_JPEG_BUF_SIZE  (40U * 1024U)

/* ---------- UDP fragment config ---------- */
#define VID_MAGIC0          0xA5U
#define VID_MAGIC1          0x5AU
#define VID_HDR_SIZE        16U
#define VID_PAYLOAD_MAX     1000U

/*
 * Minimum ms between successive UDP chunk writes.
 * CH395 needs time to push the previous packet onto the wire before
 * we can write the next one. 1 ms is enough at 100 Mbps; 2 ms is safe.
 * Setting this too low (0) causes the chip to drop packets.
 */
#define DEMO_INTER_CHUNK_DELAY_MS   1U

/* ---------- Globals (internal SRAM, DMA2-accessible) ---------- */
static uint32_t g_jpeg_buf[DEMO_JPEG_BUF_SIZE / sizeof(uint32_t)];
static uint8_t  g_send_buf[VID_HDR_SIZE + VID_PAYLOAD_MAX + 8U];
static uint8_t  g_recv_buf[64U];

static volatile uint8_t    g_net_ready = 0U;
static atk_mo395q_socket_t g_socket;

/* ---------- MO395Q callbacks ---------- */
static void phy_conn_cb(uint8_t phy_status)
{
    printf("[NET] PHY Connected (status=%u)\r\n", phy_status);
}

static void phy_disconn_cb(void)
{
    printf("[NET] PHY Disconnected\r\n");
    g_net_ready = 0U;
}

static void socket_open_cb(atk_mo395q_socket_t *socket)
{
    printf("[NET] Socket ready -> %d.%d.%d.%d:%d\r\n",
           socket->des_ip[0], socket->des_ip[1],
           socket->des_ip[2], socket->des_ip[3], socket->des_port);
    g_net_ready = 1U;
}

static void socket_close_cb(atk_mo395q_socket_t *socket)
{
    (void)socket;
    printf("[NET] Socket closed\r\n");
    g_net_ready = 0U;
}

/* ---------- Network handler helper ----------
 * Call this whenever we need to pump network events.
 * count = number of handler iterations; delay_between = ms between each.
 */
static void net_pump(uint8_t count, uint8_t delay_between_ms)
{
    uint8_t i;
    for (i = 0U; i < count; i++) {
        atk_mo395q_handler();
        if (delay_between_ms > 0U) {
            delay_ms(delay_between_ms);
        }
    }
}

/* ---------- UDP fragmented send ---------- */
static void vid_hdr_write(uint8_t *p, uint32_t frame_id,
                          uint16_t chunk_idx, uint16_t chunk_cnt,
                          uint32_t jpeg_len,  uint16_t payload_len)
{
    p[0] = VID_MAGIC0;
    p[1] = VID_MAGIC1;
    memcpy(&p[2],  &frame_id,    4U);
    memcpy(&p[6],  &chunk_idx,   2U);
    memcpy(&p[8],  &chunk_cnt,   2U);
    memcpy(&p[10], &jpeg_len,    4U);
    memcpy(&p[14], &payload_len, 2U);
}

static void send_jpeg_udp(const uint8_t *jpeg, uint32_t jpeg_len, uint32_t frame_id)
{
    uint16_t chunk_cnt;
    uint16_t ci;
    uint32_t off;
    uint16_t plen;

    if ((jpeg == NULL) || (jpeg_len == 0U)) {
        return;
    }

    chunk_cnt = (uint16_t)((jpeg_len + VID_PAYLOAD_MAX - 1U) / VID_PAYLOAD_MAX);

    for (ci = 0U; ci < chunk_cnt; ci++) {
        off  = (uint32_t)ci * VID_PAYLOAD_MAX;
        plen = (off + VID_PAYLOAD_MAX <= jpeg_len)
               ? (uint16_t)VID_PAYLOAD_MAX
               : (uint16_t)(jpeg_len - off);

        vid_hdr_write(g_send_buf, frame_id, ci, chunk_cnt, jpeg_len, plen);
        memcpy(g_send_buf + VID_HDR_SIZE, jpeg + off, plen);

        atk_mo395q_cmd_write_send_buf_sn(g_socket.socket_index,
                                         g_send_buf,
                                         (uint16_t)(VID_HDR_SIZE + plen));

        /* Give CH395 time to push the packet before writing the next one.
         * Pump the handler twice inside the delay window so events are processed. */
        delay_ms(DEMO_INTER_CHUNK_DELAY_MS);
        atk_mo395q_handler();
        atk_mo395q_handler();
    }
}

/* ---------- Main entry ---------- */
void demo_run(void)
{
    uint8_t  ret;
    uint8_t  *p;
    uint32_t  idx;
    uint32_t  jpeg_start;
    uint32_t  jpeg_end;
    uint32_t  jpeg_len;
    uint32_t  frame_id  = 0U;
    uint32_t  poll_cnt  = 0U;

    uint8_t local_ip[4] = {DEMO_LOCAL_IP_1, DEMO_LOCAL_IP_2,
                            DEMO_LOCAL_IP_3, DEMO_LOCAL_IP_4};
    uint8_t gateway[4]  = {DEMO_GW_1, DEMO_GW_2, DEMO_GW_3, DEMO_GW_4};
    uint8_t netmask[4]  = {DEMO_MASK_1, DEMO_MASK_2, DEMO_MASK_3, DEMO_MASK_4};

    printf("\r\n[SYS] Camera UDP demo (bare-metal)\r\n");
    printf("[SYS] STM32 %d.%d.%d.%d -> PC %d.%d.%d.%d:%d\r\n",
           local_ip[0], local_ip[1], local_ip[2], local_ip[3],
           DEMO_PC_IP_1, DEMO_PC_IP_2, DEMO_PC_IP_3, DEMO_PC_IP_4, DEMO_PC_PORT);

    /* ---- 1. Init MO395Q network module ---- */
    ret = atk_mo395q_init();
    if (ret != ATK_MO395Q_EOK) {
        printf("[NET] MO395Q init FAILED (%u)!\r\n", ret);
        while (1) { LED0_TOGGLE(); delay_ms(200); }
    }
    atk_mo395q_net_config(ATK_MO395Q_DISABLE, local_ip, gateway, netmask,
                          phy_conn_cb, phy_disconn_cb, NULL);

    /* ---- 2. Configure UDP socket 0 ---- */
    memset(&g_socket, 0, sizeof(g_socket));
    g_socket.socket_index = ATK_MO395Q_SOCKET_0;
    g_socket.enable       = ATK_MO395Q_ENABLE;
    g_socket.proto        = ATK_MO395Q_SOCKET_UDP;
    g_socket.des_ip[0]    = DEMO_PC_IP_1;
    g_socket.des_ip[1]    = DEMO_PC_IP_2;
    g_socket.des_ip[2]    = DEMO_PC_IP_3;
    g_socket.des_ip[3]    = DEMO_PC_IP_4;
    g_socket.des_port     = DEMO_PC_PORT;
    g_socket.sour_port    = DEMO_LOCAL_PORT;
    g_socket.send.buf     = g_send_buf;
    g_socket.send.size    = sizeof(g_send_buf);
    g_socket.recv.buf     = g_recv_buf;
    g_socket.recv.size    = sizeof(g_recv_buf);
    g_socket.open_cb      = socket_open_cb;
    g_socket.close_cb     = socket_close_cb;
    atk_mo395q_socket_config(&g_socket);

    /* ---- 3. Init ATK-MC5640 camera ---- */
    ret  = atk_mc5640_init();
    ret += atk_mc5640_set_output_format(ATK_MC5640_OUTPUT_FORMAT_JPEG);
    ret += atk_mc5640_set_light_mode(ATK_MC5640_LIGHT_MODE_ADVANCED_AWB);
    ret += atk_mc5640_set_color_saturation(ATK_MC5640_COLOR_SATURATION_4);
    ret += atk_mc5640_set_brightness(ATK_MC5640_BRIGHTNESS_4);
    ret += atk_mc5640_set_contrast(ATK_MC5640_CONTRAST_4);
    ret += atk_mc5640_set_hue(ATK_MC5640_HUE_6);
    ret += atk_mc5640_set_special_effect(ATK_MC5640_SPECIAL_EFFECT_NORMAL);
    ret += atk_mc5640_set_exposure_level(ATK_MC5640_EXPOSURE_LEVEL_5);
    ret += atk_mc5640_set_sharpness_level(ATK_MC5640_SHARPNESS_OFF);
    ret += atk_mc5640_set_mirror_flip(ATK_MC5640_MIRROR_FLIP_1);
    ret += atk_mc5640_set_test_pattern(ATK_MC5640_TEST_PATTERN_OFF);
    ret += atk_mc5640_set_pre_scaling_window(4, 0);
    ret += atk_mc5640_set_output_size(DEMO_CAM_WIDTH, DEMO_CAM_HEIGHT);
    if (ret != 0U) {
        printf("[CAM] Init FAILED (%u)!\r\n", ret);
        while (1) { LED0_TOGGLE(); delay_ms(200); }
    }

    /* ---- 4. Autofocus ----
     *
     * auto_focus_init()       : uploads VCM firmware; polls up to 5000 ms
     * auto_focus_continuance(): starts continuous AF; polls up to 10000 ms
     *
     * Both functions block with delay_ms(1) loops, so we interleave
     * net_pump() calls every 50 ms to keep the CH395 alive while waiting.
     * This is done by letting the AF functions complete on their own
     * (they return when done or timeout) and then pumping the network.
     *
     * NOTE: we do NOT call auto_focus_once() because it also blocks up to
     * 5000 ms and the lens movement is handled by continuance mode anyway.
     */
    ret = atk_mc5640_auto_focus_init();
    /* After firmware upload, pump network to process any pending events. */
    net_pump(10, 5);   /* 10 x 5 ms = 50 ms of network handling */

    if (ret == ATK_MC5640_EOK) {
        ret = atk_mc5640_auto_focus_continuance();
        /* Pump network again after continuance setup. */
        net_pump(10, 5);
        if (ret == ATK_MC5640_EOK) {
            printf("[CAM] Autofocus continuous OK\r\n");
        } else {
            printf("[CAM] Autofocus continuance timeout, fixed focus\r\n");
        }
    } else {
        printf("[CAM] Autofocus init failed, fixed focus\r\n");
    }

    printf("[CAM] Ready %ux%u JPEG -> UDP\r\n", DEMO_CAM_WIDTH, DEMO_CAM_HEIGHT);

    /* ---- 5. Main loop ---- */
    while (1) {
        /* Must call handler continuously to maintain network connection. */
        atk_mo395q_handler();

        if (g_net_ready == 0U) {
            poll_cnt++;
            if (poll_cnt >= 5000U) {
                poll_cnt = 0U;
                printf("[NET] Waiting PHY/socket...\r\n");
            }
            delay_ms(1);
            continue;
        }

        /* Capture one JPEG frame via DCMI DMA (official path:
         * DTS_32B_INC + DCMI_JPEG_DISABLE, search FFD8/FFD9 manually). */
        p = (uint8_t *)g_jpeg_buf;
        memset(g_jpeg_buf, 0, DEMO_JPEG_BUF_SIZE);
        atk_mc5640_get_frame((uint32_t)g_jpeg_buf,
                             ATK_MC5640_GET_TYPE_DTS_32B_INC, NULL);

        /* Search SOI FF D8 */
        jpeg_start = UINT32_MAX;
        for (idx = 0U; idx < DEMO_JPEG_BUF_SIZE - 1U; idx++) {
            if ((p[idx] == 0xFFU) && (p[idx + 1U] == 0xD8U)) {
                jpeg_start = idx;
                break;
            }
        }
        if (jpeg_start == UINT32_MAX) {
            continue;
        }

        /* Search EOI FF D9 */
        jpeg_end = UINT32_MAX;
        for (idx = jpeg_start + 2U; idx < DEMO_JPEG_BUF_SIZE - 1U; idx++) {
            if ((p[idx] == 0xFFU) && (p[idx + 1U] == 0xD9U)) {
                jpeg_end = idx;
                break;
            }
        }
        if (jpeg_end == UINT32_MAX) {
            continue;
        }

        jpeg_len = jpeg_end - jpeg_start + 2U;
        send_jpeg_udp(p + jpeg_start, jpeg_len, frame_id++);
        LED0_TOGGLE();
    }
}
