# File: config.py
# Configuration file for constants
from settings import settings as app_settings

API_SERVER_HOST = app_settings.API_SERVER_HOST
API_SERVER_PORT = app_settings.API_SERVER_PORT
API_LOG_LEVEL = app_settings.API_LOG_LEVEL

THRESHOLD_DETECT = 0.4
THRESHOLD_COVERAGE = 0.5

ICS_URL = "http://192.168.1.30:7000/ics/taskOrder/addTask"  # Replace with actual URL
PROCESSING_LOOP_DELAY = 1  # seconds

# Snapshot configuration
ENABLE_SNAPSHOTS = False
SNAPSHOT_DIR = "snapshots"
SNAPSHOT_QUALITY = 95  # JPEG quality (0-100)

USE_GPU_DECODE = True
GPU_DECODE_BUFFER_SIZE = 10**8  # 100MB buffer for subprocess pipe
FFMPEG_RECONNECT_DELAY = 1.0    # seconds
FFMPEG_MAX_RETRIES = 5

INFERENCE_MAX_QUEUE_SIZE = 500
INFERENCE_MAX_BATCH_SIZE = 32
INFERENCE_BATCH_TIMEOUT = 1 
INFERENCE_NUM_STREAMS = 3
MODEL_PATH = "models/ModelHN_160326_02.engine"


END_POINT_EMPTY = "end_10001546" #10001546

# Pairs theo vùng để GUI hiển thị 2 cột (AE | AF)
PAIRS_AE_5 = [
    # AE5
    ("start_10000060", "end_10000760"),
    ("start_10000059", "end_10000761"),
    ("start_10001050", "end_10000759"),
    ("start_10001051", "end_10000385"),
    ("start_10001052", "end_10000382"),
    ("start_10001053", "end_10000376"),
    ("start_10001054", "end_10000373"),
    ("start_10001055", "end_10000367"),
    ("start_10001056", "end_10000394"),
    ("start_10001057", "end_10000370"),
    
    # xe chuyên dụng
    ("start_10000062", "end_10000396"),
    ("start_10002232", "end_10000361"),
    ("start_10002233", "end_10000364"),
    ("start_10001762", "end_10001495"),
    ("start_10001763", "end_10000379"),

    ### Xe trống AE5
    ("start_10000391",),
    ("start_10001287",),
    ("start_10001290",),
    ("start_10001293",),
    ("start_10001295",),
    ("start_10001299",),

    ("start_10001384", "end_10000044"),
    ("start_10001384", "end_10000045"),
    ("start_10001384", "end_10000046"),
    ("start_10001384", "end_10000047"),

    ("start_10001385", "end_10000044"),
    ("start_10001385", "end_10000045"),
    ("start_10001385", "end_10000046"),
    ("start_10001385", "end_10000047"),

    ("start_10001386", "end_10000044"),
    ("start_10001386", "end_10000045"),
    ("start_10001386", "end_10000046"),
    ("start_10001386", "end_10000047")
]

PAIRS_AE_6 = [
    #------------------ AE6 point ------------------
    ("start_10000037", "end_10000276"),
    ("start_10000038", "end_10000282"),
    ("start_10000039", "end_10000280"),
    ("start_10000040", "end_10000284"),
    ("start_10000041", "end_10000286"),
    ("start_10000042", "end_10000288"),
    ("start_10000989", "end_10000757"),
    ("start_10000992", "end_10000758"),

    # xe chuyên dụng
    ("start_10000063", "end_10000266"),
    ("start_10000749", "end_10000270"),
    ("start_10000748", "end_10000268"),
    ("start_10000747", "end_10000913"),
    ("start_10000746", "end_10001793"),
    ("start_10000745", "end_10000290"),
    ("start_10000744", "end_10001797"),
    ("start_10000743", "end_10001796"),

    #### Xe trống AE6
    #("start_10000910", "end_10001386"),
    #("start_10000907", "end_10001386"),
    # ("start_10000484", "end_10001386"), #AE6-XT5
    # ("start_10000481", "end_10001386"), #AE6-XT6
    #("start_10000478", "end_10001386"), #AE6-XT7 
    ("start_10000476",), #AE6-XT8
    ("start_10000473",), #AE6-XT9
    ("start_10000904",) #AE6-XT3
]


PAIRS_SUB_5 = [
    ("start_10002090", "end_10001492"), #34-73 5L2-1
    ("start_10002091", "end_10001490"), #34-73 5L2-2
    ("start_10002088", "end_10001485"), #34-73 5L2-3
    ("start_10002086", "end_10001489"), #34-73 5L2-4
    ("start_10002084", "end_10001343"), #34-73 5L2-5
    ("start_10002082", "end_10001344") #34-73 5L2-6



    ### Xe trống
    # ("start_10000776", "end_10001546"),
    # ("start_10000782", "end_10001546"),
    # ("start_10001843", "end_10002171"),

]

# # Tách SUB theo khu vực để hiển thị GUI
# PAIRS_5L = PAIRS_SUB[:5]
# PAIRS_6L = PAIRS_SUB[5:]

# GUI theo vùng
VALIDATE_PAIRS_BY_ZONE = {
    "AE5": PAIRS_AE_5,
    "AE6": PAIRS_AE_6,
    #"AF": PAIR_AF,
    #"5L": PAIRS_5L,
    #"6L": PAIRS_6L,
}
VALIDATE_PAIRS = set(PAIRS_AE_5 + PAIRS_AE_6) #+ PAIR_AF + PAIRS_5L + PAIRS_6L)

# Simulate camera data (rtsp, rois, node_ids) - in real, import from camera_service.py
FALLBACK_CAMERAS_OLD = [

    # -----------------AE5 CAMERA ------------------
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102", #AE
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10000060", "roi": [163, 156, 79, 66]},
            {"node_id": "start_10000059", "roi": [491, 139, 73, 80]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.103:554/Streaming/Channels/102", #xe chuyên dụng chưa dùng
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10001763", "roi": [200, 217, 45, 90]},
            {"node_id": "start_10001762", "roi": [247, 213, 45, 103]},
            {"node_id": "start_10002233", "roi": [293, 218, 42, 101]},
            {"node_id": "start_10002232", "roi": [347, 257, 89, 66]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.104:554/Streaming/Channels/102", #xe chuyên dụng chưa dùng
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10000062", "roi": [268, 274, 80, 62]},
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.105:554/Streaming/Channels/102", # not recognize AE
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10001057", "roi": [175, 93, 79, 62]},
            {"node_id": "start_10001056", "roi": [171, 162, 84, 74]},
            {"node_id": "start_10001055", "roi": [164, 233, 89, 75]},
            {"node_id": "start_10001054", "roi": [160, 312, 89, 69]},
           # {"node_id": "start_10001058", "roi": [405, 92, 61, 109]}
        ]
    },
    { 
        "rtsp": "rtsp://admin:Thado12@@192.168.1.106:554/Streaming/Channels/102", #low conf + not recognize  AE
        "zone": "AE5",
        "rois": [
           # {"node_id": "start_10001059", "roi": [160, 156, 79, 71]},
            {"node_id": "start_10001050", "roi": [403, 77, 87, 65]},
            {"node_id": "start_10001051", "roi": [405, 158, 86, 71]},
            {"node_id": "start_10001052", "roi": [402, 245, 88, 72]},
            {"node_id": "start_10001053", "roi": [399, 326, 99, 72]}
        ]
    },

    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.110:554/Streaming/Channels/102", # trái sang phải AE
        "zone": "AE5",
        "rois": [
            {"node_id": "end_10000759", "roi": [89, 158, 108, 148]},
            {"node_id": "end_10000760", "roi": [217, 154, 136, 148]},
            {"node_id": "end_10000761", "roi": [356, 139, 111, 151]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.111:554/Streaming/Channels/102", #AE
        "zone": "AE5",
        "rois": [
            {"node_id": "end_10000396", "roi": [157, 154, 99, 105]},
            {"node_id": "end_10000394", "roi": [367, 195, 111, 55]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.112:554/Streaming/Channels/102",#AE
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10000391", "roi": [25, 234, 107, 85]},
            {"node_id": "end_10000388", "roi": [145, 244, 108, 75]},
            {"node_id": "end_10000385", "roi": [258, 235, 121, 76]},
            {"node_id": "end_10000382", "roi": [376, 228, 124, 78]}
        ]
    },

    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.113:554/Streaming/Channels/102", 
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10001287", "roi": [253, 185, 134, 142]}
            ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.115:554/Streaming/Channels/102",
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10001290", "roi": [220, 212, 166, 109]}
            ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.114:554/Streaming/Channels/102", #qr code AE
        "zone": "AE5",
        "rois": [
            {"node_id": "end_10000379", "roi": [68, 205, 88, 149]},
            {"node_id": "end_10000376", "roi": [163, 199, 122, 164]},
            {"node_id": "end_10000373", "roi": [306, 200, 115, 160]},
            {"node_id": "end_10000370", "roi": [426, 209, 95, 143]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.116:554/Streaming/Channels/102", #qr_code AE
        "zone": "AE5",
        "rois": [
            {"node_id": "end_10000367", "roi": [193, 108, 63, 86]},
            {"node_id": "end_10000364", "roi": [262, 77, 53, 109]}, 
            {"node_id": "end_10000361", "roi": [321, 76, 57, 108]}, 
            {"node_id": "start_10001293", "roi": [207, 352, 188, 125]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.117:554/Streaming/Channels/102", #AE
        "zone": "AE5",
        "rois": [
            {"node_id": "start_10001299", "roi": [92, 356, 120, 90]},
            {"node_id": "start_10001295", "roi": [468, 242, 140, 93]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.118:554/Streaming/Channels/102", #AE
        "zone": "AE5",
        "rois": [
            {"node_id": "end_10001495", "roi": [420, 98, 124, 137]} 
        ]
    },


    # -----------------AE6 CAMERA ------------------
    #### ---- Xe cấp -----
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.107:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000037", "roi": [151, 258, 58, 111]},
            {"node_id": "start_10000038", "roi": [217, 268, 48, 113]},
            {"node_id": "start_10000039", "roi": [276, 278, 46, 110]},
            {"node_id": "start_10000040", "roi": [326, 282, 51, 115]},
            {"node_id": "start_10000041", "roi": [381, 290, 56, 113]},
            {"node_id": "start_10000042", "roi": [434, 298, 55, 108]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.119:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "end_10000266", "roi": [400, 218, 91, 39]},
            {"node_id": "end_10000758", "roi": [166, 165, 20, 79]},
            {"node_id": "end_10000757", "roi": [234, 249, 62, 104]},
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.120:554/Streaming/Channels/102",
        "rois": [
            {"node_id": "end_10000913", "roi": [214, 289, 119, 120]},
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.121:554/Streaming/Channels/102", 
        "zone": "AE6",
        "rois": [
            {"node_id": "end_10000276", "roi": [231, 210, 90, 218]}
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.122:554/Streaming/Channels/102", 
        "zone": "AE6",
        "rois": [
            {"node_id": "end_10000270", "roi": [302, 113, 82, 177]}, #CD2
            {"node_id": "end_10000268", "roi": [228, 122, 65, 177]}, #CD3
        ]
    },
    # {
    #     "rtsp": "rtsp://admin:Thado12@@192.168.1.123:554/Streaming/Channels/102", 
    #     "zone": "AE6",
    #     "rois": [
    #         {"node_id": "start_10000910", "roi": [191, 258, 105, 91]}, #AE6-XT1
    #         {"node_id": "start_10000907", "roi": [321, 267, 89, 89]}, #AE6-XT2
    #     ]
    # },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.124:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "end_10000280", "roi": [221, 90, 106, 202]}, #-6C3
            {"node_id": "end_10000282", "roi": [326, 88, 96, 205]}, #-6C2
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.126:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "end_10000290", "roi": [190, 135, 94, 188]}, #CD6
            {"node_id": "end_10001797", "roi": [110, 145, 74, 172]}, #CD7
            {"node_id": "end_10000288", "roi": [289, 150, 96, 174]}, #-6C6
            {"node_id": "end_10000286", "roi": [389, 226, 51, 74]}, #-6C5
            {"node_id": "end_10000284", "roi": [476, 151, 64, 167]} #-6C4
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.127:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            #{"node_id": "start_10000478", "roi": [84, 177, 95, 89]}, #AE6-XT7
            {"node_id": "start_10000476", "roi": [198, 179, 88, 81]}, #AE6-XT8
            {"node_id": "start_10000473", "roi": [290, 173, 104, 81]} #AE6-XT9
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.171:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000904", "roi": [148, 216, 104, 95]}, #AE6-XT3
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.141:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000989", "roi": [357, 244, 45, 97]} #6B-
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.142:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000992", "roi": [192, 110, 34, 89]}, #6A-
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.140:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000063", "roi": [266, 213, 88, 74]}, 
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.139:554/Streaming/Channels/102",
        "zone": "AE6",
        "rois": [
            {"node_id": "start_10000749", "roi": [467, 183, 67, 107]}, #CD2
            {"node_id": "start_10000748", "roi": [414, 187, 43, 106]}, #CD3
            {"node_id": "start_10000747", "roi": [352, 189, 60, 10]}, #CD4
            {"node_id": "start_10000746", "roi": [311, 190, 35, 104]}, #CD5
            {"node_id": "start_10000745", "roi": [252, 188, 49, 106]}, #CD6
            {"node_id": "start_10000744", "roi": [206, 191, 37, 97]}, #CD7
            {"node_id": "start_10000743", "roi": [159, 191, 35, 97]}, #CD8
        ]
    },
    {
        "rtsp": "rtsp://admin:Thado12@@192.168.1.128:554/Streaming/Channels/102",
        "rois": [
            {"node_id": "end_10001793", "roi": [295, 124, 81, 205]}, #CD5
            {"node_id": "end_10001796", "roi": [382, 129, 76, 206]}, #CD8
        ]
    },
    
    # Camera 194: xe trống (không thuộc AE5/AE6), chỉ bật/tắt bằng Start All hoặc nút Cam
    { 
        "rtsp": "rtsp://admin:Thado12@@192.168.1.194:554/Streaming/Channels/102", 
        "rois": [
           # {"node_id": "start_10001059", "roi": [160, 156, 79, 71]},
           # {"node_id": "end_10002018", "roi": [292, 235, 86, 156]},
           # {"node_id": "end_10001239", "roi": [226, 386, 86, 59]},
           {"node_id": "start_10001384", "roi": [292, 241, 76, 141]},
           {"node_id": "start_10001385", "roi": [375, 240, 74, 146]},
           {"node_id": "start_10001386", "roi": [465, 247, 75, 134]},
           {"node_id": "start_10001387", "roi": [452, 119, 84, 115]}
        ]
    },

        # Camera 109: xe sạch
    { 
        "rtsp": "rtsp://admin:Thado12@@192.168.1.109:554/Streaming/Channels/102", 
        "rois": [
           # {"node_id": "start_10001059", "roi": [160, 156, 79, 71]},
           # {"node_id": "end_10002018", "roi": [292, 235, 86, 156]},
           {"node_id": "end_10000044", "roi": [107, 235, 93, 93]},
           {"node_id": "end_10000045", "roi": [207, 238, 98, 89]},
           {"node_id": "end_10000046", "roi": [308, 231, 100, 94]},
           {"node_id": "end_10000047", "roi": [409, 243, 79, 77]}
        ]
    }
]

# ---------------------------------------------------------------------------
# CAMERAS schema mới
# ---------------------------------------------------------------------------
# Hiện trong repo đang có CAMERAS format cũ:
# - cam["rtsp"]
# - cam["zone"]
# - cam["rois"] = list[{"node_id": "start_...|end_...", "roi": [x,y,w,h]}]
#
# Bạn yêu cầu CAMERAS chuyển sang schema mới:
# - cam["url"] tương ứng cam["rtsp"]
# - cam["area_name"] tương ứng cam["zone"]
# - cam["cameraId"] là index trong mảng
# - cam["rois"] = dict { "<numeric_id>": {"roi":[x,y,w,h], "start":bool, "end":bool} }
#
# Trong khi bạn chưa paste toàn bộ dữ liệu schema mới, đoạn code dưới sẽ
# tự chuyển đổi từ format cũ sang format mới để không cần sửa tay từng camera.

_CAMERAS_OLD = FALLBACK_CAMERAS_OLD


def _roi_list_to_rois_dict(rois_list):
    rois_dict = {}
    for roi_dict in rois_list or []:
        node_id = roi_dict.get("node_id")
        roi = roi_dict.get("roi")
        if not node_id or roi is None:
            continue

        if node_id.startswith("start_"):
            key = node_id[len("start_") :]
            rois_dict[key] = {"roi": roi, "start": True, "end": False}
        elif node_id.startswith("end_"):
            key = node_id[len("end_") :]
            rois_dict[key] = {"roi": roi, "start": False, "end": True}
        else:
            # Fallback: nếu không có prefix start_/end_ thì mặc định start=False/end=False
            key = node_id
            rois_dict[key] = {"roi": roi, "start": False, "end": False}
    return rois_dict


FALLBACK_CAMERAS = [
    {
        "url": cam.get("rtsp"),
        "cameraId": i,  # index trong mảng
        "source_owner": 1,
        "type_model": 1,
        "node_id": 1,
        "area_name": cam.get("zone"),
        "rois": _roi_list_to_rois_dict(cam.get("rois", [])),
    }
    for i, cam in enumerate(_CAMERAS_OLD)
]

# Load camera config from MongoDB (optional). Fallback to hardcoded config if DB is unavailable.
CAMERAS = FALLBACK_CAMERAS
try:
    mongodb_url = getattr(app_settings, "MongoDB_URL", None)
    mongodb_db = getattr(app_settings, "MongoDB_DB", "HONDA_HN")
    if mongodb_url:
        from core.camera_config_repository import load_cameras_from_mongodb

        _db_cameras = load_cameras_from_mongodb(
            mongodb_url=mongodb_url,
            db_name=mongodb_db,
            collection_name="node_id",
        )
        if _db_cameras:
            CAMERAS = _db_cameras
except Exception:
    CAMERAS = FALLBACK_CAMERAS


# Set RTSP theo từng khu vực (lọc từ CAMERAS theo area_name)
RTSP_AE5 = set(c.get("url") for c in CAMERAS if c.get("area_name") == "AE5" and c.get("url"))
RTSP_AE6 = set(c.get("url") for c in CAMERAS if c.get("area_name") == "AE6" and c.get("url"))
# RTSP_5L = set(c["rtsp"] for c in CAMERAS if c.get("zone") == "5L")
# RTSP_6L = set(c["rtsp"] for c in CAMERAS if c.get("zone") == "6L")
# RTSP_AF = set(c["rtsp"] for c in CAMERAS if c.get("zone") == "AF")