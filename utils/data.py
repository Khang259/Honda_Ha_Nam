from datetime import datetime
import uuid

def payload_sent_ICS(start_point, end_point):
    uid = uuid.uuid4().hex
    now = datetime.now()
    start_num = ''.join(filter(str.isdigit, str(start_point)))
    end_num = ''.join(filter(str.isdigit, str(end_point)))
    
    data_car = {
            "modelProcessCode": "SingleGroupAE5", #"moveShelf17",
            "fromSystem": "ICS",
            "orderId": f"S-{start_num}-{end_num}-{now}",
            "taskOrderDetail": [
                {"taskPath": f"{start_num},{end_num}"}
            ]
        }
    return data_car

def payload_sent_ICS_empty(start_num, end_point_empty):
    now = datetime.now()
    start_empty = ''.join(filter(str.isdigit, str(start_num)))
    end_empty = ''.join(filter(str.isdigit, str(end_point_empty)))

    data_empty_car = {
        "modelProcessCode": "SEGroupAE",
        "fromSystem": "ICS",
        "orderId": f"E-{start_empty}-{now}",
        "taskOrderDetail": [
            {"taskPath": f"{start_empty},{end_empty}"}
        ]
    }
    return data_empty_car

def payload_sent_ICS_double(start_num, end_num, start_empty_num, end_empty_num):
    now = datetime.now()
    start_num = ''.join(filter(str.isdigit, str(start_num)))
    end_num = ''.join(filter(str.isdigit, str(end_num)))
    start_empty_num = ''.join(filter(str.isdigit, str(start_empty_num)))
    end_empty_num = ''.join(filter(str.isdigit, str(end_empty_num)))

    data_double_car = {
        "modelProcessCode": "DoubleGroupAE",  # "moveShelf17",
        "fromSystem": "ICS",
        "orderId": f"D-AE-{start_num}-{end_num}-{start_empty_num}-{now}",
        "taskOrderDetail": [
            {"taskPath": f"{start_num},{end_num}"},
            {"taskPath": f"{start_empty_num},{end_empty_num}"}
        ]
    }
    return data_double_car