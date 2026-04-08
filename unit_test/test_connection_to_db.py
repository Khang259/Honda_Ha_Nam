from pymongo import MongoClient
c = MongoClient("mongodb://192.168.1.30:27017/")
db = c["Honda_AI"]
print(db.list_collection_names())
print(db["node_id"].count_documents({}))
print(db["node_id"].find_one())