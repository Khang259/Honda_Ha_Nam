import requests
import time

start = time.time()

r = requests.post("http://192.168.1.100:7000/ics/taskOrder/addTask", 
                    json={
                            "modelProcessCode": "testGroup", #"moveShelf17",
                            "fromSystem": "ICS",
                            "orderId": "1234567890",
                            "taskOrderDetail": [
                                {"taskPath": "10000060,10000760"}
                            ]
                        })

end = time.time()

print("Total time:", (end - start) * 1000, "ms")
