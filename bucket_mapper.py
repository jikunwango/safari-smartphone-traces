class Location:
    
    def __init__(self) -> None:
        self.bucket_id = 0
        self.sub_id = 0
        self.row_id = 0
        self.location_dict = {}
    def addr(self)->int:
        return 1

class Bucket:
    def __init__(self) -> None:
        self.buckets=[]
        self.bucket_idx=[]
        self.location_dict = {}
        pass

    def push(self,bk_id,sub_id,addr):
        current_idx = self.bucket_idx[bk_id][sub_id]
        if current_idx>=511:
            self.bucket_idx[bk_id][sub_id]=0
        
        self.location_dict[addr]= Location(bk_id,sub_id,current_idx)

    def get_location(self,addr):
        return self.location_dict[addr]


def map():
    file_path = "output/convert/c_cases/c_case0.trace"
    map_result = []
    bucket_idx_arr  = []
    bucket_id = 0
    subarray_id = 0
    bucket = Bucket()
    with open(file_path,"r") as file:
        while file.readable():
            rd = file.readline()
            wr = file.readline()

            rd_addr = rd.split()[1]
            wr_addr = wr.split()[2]

            rd_location = bucket.get_location(rd_addr)
            wr_location = bucket.get_location(wr_addr)

            if rd_location == None and wr_location ==None:
                # no rows hit
                rd_location = bucket.push(rd_addr)
                wr_location = bucket.push(wr_addr)
            elif rd_location == None:
                rd_location = bucket.push(rd_addr)
            elif wr_location ==None:
                wr=bucket.push(rd_addr)

            map_result.append("0 {}".format(rd_location.addr))
            map_result.append("0 -1 {}".format(wr_location.addr))
