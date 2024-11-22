import math
import address_helper as ah


class CMD:
    READ = "RD"
    WRITE = "WR"
    RC = "RC"


class CMDLine:

    def __init__(self, op, addr1, addr2) -> None:
        self.op = op
        self.addr1 = addr1
        self.addr2 = addr2


class CMD4Window:
    row_bits = ah.g_assemble_levels_bits[4]
    subarray_mask_bits = ah.g_assemble_levels_bits[4] + int(
        math.log2(ah.g_subarray_size)
    )
    tx_offset = ah.g_tx_offset

    def __init__(self, target: int, alternative: bool, replace_with_rowclone: bool):
        self.win: list[CMDLine] = []
        self.cap = 4
        self.traces = []
        self.row_clone_count = 0
        self.handled_rows = 0
        self.target_row_num = target
        self.alternative = alternative
        self.row_requests = []
        self.replace_with_rowclone = replace_with_rowclone
        self.error_row_clone = 0
    def is_full(self) -> bool:
        return len(self.win) >= self.cap

    def is_empty(self) -> bool:
        return len(self.win) == 0

    def add(self, row: CMDLine):
        if len(self.row_requests) >= self.target_row_num:
            return
        self.win.append(row)
        if row.op == CMD.READ:
            self.row_requests.append(
                "<read>  " + str(ah.address_to_byte_level(row.addr1))
            )
        else:
            self.row_requests.append(
                "<write>  " + str(ah.address_to_byte_level(row.addr2))
            )

    def clear(self):
        self.win.clear()

    def is_finished(self):
        return self.handled_rows >= self.target_row_num

    def extend_traces(self, lines: list):
        self.traces.extend(lines)

    def split_2rows_to64(row1: CMDLine, row2: CMDLine, alternative: bool):
        cache_lines = []
        if not alternative:
            cache_lines.extend(CMD4Window.simple_split_to64(row1))
            cache_lines.extend(CMD4Window.simple_split_to64(row2))
        else:
            read_addr = row1.addr1
            write_addr = row2.addr2
            for cl in range(64):
                rd_cl = (read_addr & ~((1 << CMD4Window.row_bits) - 1)) + (
                    cl << CMD4Window.tx_offset
                )
                cache_lines.append("0 {}".format(rd_cl))
                wr_cl = (write_addr & ~((1 << CMD4Window.row_bits) - 1)) + (
                    cl << CMD4Window.tx_offset
                )
                cache_lines.append("0 -1 {}".format(wr_cl))
        return cache_lines

    def simple_split_to64(row: CMDLine, dma:bool=False):
        cache_lines = []
        if row.op == CMD.READ:
            addr = row.addr1
        else:
            addr = row.addr2
        for cl in range(64):
            rd_cl = (addr & ~((1 << CMD4Window.row_bits) - 1)) + (
                cl << CMD4Window.tx_offset
            )
            if row.op == CMD.READ:
                cache_lines.append("0 {}".format(rd_cl))
            else:
                if dma:
                    cache_lines.append("0 -2 {}".format(rd_cl))
                else:
                    cache_lines.append("0 -1 {}".format(rd_cl))
        return cache_lines

    def is_copy_window(self):
        if self.is_full() == False:
            return False
        # 4 row in windows should follow such order
        # write row1 -> read row1 -> write row2 -> read row2
        if (
            self.win[0].op != CMD.WRITE
            or self.win[1].op != CMD.READ
            or self.win[0].addr2 != self.win[1].addr1
        ):
            return False
        if (
            self.win[2].op != CMD.WRITE
            or self.win[3].op != CMD.READ
            or self.win[2].addr2 != self.win[3].addr1
        ):
            return False
        return True

    def handle_in_normal_mode(self):
        # we only handle 1st row
        if self.is_empty():
            return
        row1 = self.win.pop(0)
        self.extend_traces(CMD4Window.simple_split_to64(row1))
        self.handled_rows += 1
        return

    def handle_copy_window(self) -> list:
        # if yes, then check if we can replace with a rowclone
        rd_addr = self.win[1].addr1
        wr_addr = self.win[2].addr2
        self.extend_traces(CMD4Window.simple_split_to64(self.win[0],True))
        if (
            self.replace_with_rowclone
            and rd_addr >> self.subarray_mask_bits == wr_addr >> self.subarray_mask_bits
        ):
            # replace with a rowclone command
            if rd_addr == wr_addr:
                self.error_row_clone+=1
            else:
                self.traces.append("0 {} {}".format(rd_addr, wr_addr))
                self.row_clone_count += 1
        else:
            # consider consecutive or alternative
            self.extend_traces(
                CMD4Window.split_2rows_to64(self.win[1], self.win[2], self.alternative)
            )

        self.extend_traces(CMD4Window.simple_split_to64(self.win[3]))
        self.clear()
        self.handled_rows += 4
        return

    def handle(self):
        if self.is_copy_window() and (self.handled_rows <= self.target_row_num - 4):
            self.handle_copy_window()
        else:
            self.handle_in_normal_mode()


def convert_to_cacheline(
    file_path: str, limit: int, alternative: bool, replace_with_rowclone: bool
):
    slide_window = CMD4Window(
        target=limit,
        alternative=alternative,
        replace_with_rowclone=replace_with_rowclone,
    )
    with open(file_path, "r") as file:
        while True:
            while not slide_window.is_full():
                if slide_window.is_finished():
                    break
                if file.readable():
                    cmd = file.readline()
                    if cmd == "":
                        break
                    arr = cmd.split()
                    if len(arr) == 2:
                        line = CMDLine(CMD.READ, ah.mask_address(int(arr[1])), -1)
                    else:
                        line = CMDLine(CMD.WRITE, -1, ah.mask_address(int(arr[2])))
                    slide_window.add(line)
                else:
                    break
            # here the window is 4 or tail case
            slide_window.handle()
            if slide_window.is_finished():
                break
    return (
        slide_window.row_clone_count,
        len(slide_window.row_requests),
        slide_window.traces,
        slide_window.row_requests,
        slide_window.error_row_clone
    )


def convert_to_rowclone_trace(file_path: str, limit: int, alternant: bool):
    row_bits = ah.g_assemble_levels_bits[4]
    subarray_mask_bits = ah.g_assemble_levels_bits[4] + int(
        math.log2(ah.g_subarray_size)
    )
    tx_offset = ah.g_tx_offset
    row_requests = []
    traces = []
    row_clone_count = 0
    trace_line_count = 0
    with open(file_path, "r") as file:
        while file.readable():
            load_cmd = file.readline()
            store_cmd = file.readline()
            if load_cmd == "" or store_cmd == "":
                break
            if trace_line_count >= limit:
                break
            # ignore high bits
            rd_addr = ah.mask_address(int(load_cmd.split()[1]))
            wr_addr = ah.mask_address(int(store_cmd.split()[2]))
            trace_line_count += 2
            row_requests.append("<read>  " + str(ah.address_to_byte_level(rd_addr)))
            row_requests.append("<write> " + str(ah.address_to_byte_level(wr_addr)))
            # check if read and write are in the same subarray
            if rd_addr >> subarray_mask_bits == wr_addr >> subarray_mask_bits:
                # replace with a rowclone command
                traces.append("0 {} {}".format(rd_addr, wr_addr))
                row_clone_count += 1
            else:
                # split row request into 64 consecutive cache line request
                # here we have two cases, split read/write row into
                # 1>>  consecutive cache line reads then consecutive cache line writes
                # 2>>  alternant read and write in cacheline-grain
                if alternant:
                    for cl in range(64):
                        rd_cl = (rd_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 {}".format(rd_cl))
                        wr_cl = (wr_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 -1 {}".format(wr_cl))
                else:
                    for cl in range(64):
                        rd_cl = (rd_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 {}".format(rd_cl))
                    for cl in range(64):
                        wr_cl = (wr_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 -1 {}".format(wr_cl))

    return row_clone_count, trace_line_count, traces, row_requests


def convert_to4line(file_path: str, output_path: str):
    with open(file_path, "r") as file:
        with open(output_path, "w") as out:
            while file.readable():
                rd = file.readline()
                if rd == "":
                    break
                out.write("0 -1 {}".format(rd.split()[1]) + "\n")
                out.write(rd)
                wr = file.readline()
                if wr == "":
                    break
                out.write(wr)
                out.write("0 {}".format(wr.split()[2]) + "\n")


def batch_convert_to4line():
    for idx in range(6):
        for mode in ["map","unmap"]:
            convert_to4line(
                "inputs/{}_case{}.trace".format(mode,idx),
                "inputs/extend4/{}4_case{}.trace".format(mode,idx),
            )
# batch_convert_to4line()
def slice_file_intoX(file_path:str,pre:str,step:int,num:int):
        # file_path = "inputs/parent_case{}.trace".format(idx)
    with open(file_path,"r") as file:
        for idx in range(num):
            slide_file_path = "inputs/{}_slide{}.trace".format(pre,idx)
            count = 0
            with open(slide_file_path, "w") as out:
                    while file.readable() and count < step:
                        out.write(file.readline())
                        count += 1
# for file in ["parent_case1.trace","parent_case2.trace","remap.trace"]:
#     slice_file_intoX("inputs/"+file,file,30000,6)

def split_trace_into3():
    length = 400000
    case_id = 0
    for idx in range(1, 3):
        file_path = "inputs/parent_case{}.trace".format(idx)
        with open(file_path, "r") as file:
            for block in range(3):
                output_path = "inputs/case_block{}.trace".format(case_id)
                case_id += 1
                count = 0
                with open(output_path, "w") as out:
                    while file.readable() and count < length:
                        out.write(file.readline())
                        count += 1


def create_cache_traces_for_ramulator2():
    trace_count = [
        # 100,
        # 500,
        # 1000,
        # 5000,
        # 10000,
        # 50000,
        # 100000,
        # 800000,
        60000,
        # 1000000,
        # 1500000,
    ]
    alternant = True
    for baseline in ["c","m","rr"]:
        if  baseline == "c":
            replace_with_rowclone = False
            mode = "unmap"
        elif baseline =="m":
            replace_with_rowclone = True
            mode = "unmap"
        elif baseline =="rr":
            replace_with_rowclone = True
            mode = "map"
        else:
            raise Exception("error baseline!")
        
        output_dir = "output/convert/{}_cases/".format(baseline)

        for case in range(6):
            trace_file = "inputs/extend4/{}4_case{}.trace".format(mode,case)
            # output_dir = "output/convert/{}_case{}/".format(mode,case)

            for limit in trace_count:
                # 1.convert row request to cache line request
                # row_clone_count, total_request, traces, row_requests = (
                #     convert_to_rowclone_trace(trace_file, limit, alternant)
                # )
                row_clone_count, total_request, traces, row_requests, error_row_clone = convert_to_cacheline(
                    trace_file, limit, alternant, replace_with_rowclone
                )
                print(
                    "row clone request is {}, total request is {}, error row clone is {}".format(
                        row_clone_count, total_request,error_row_clone
                    )
                )
                # # 2. save row request to file
                # ah.save_to_file(
                #     row_requests,
                #     output_dir + "case{}_row_to_bytes_raw_data.txt".format(case),
                # )
                # # 3. convert cache line trace to block level
                # ah.traces_array_to_block(
                #     traces, output_dir + "{}_case{}_cache_block_raw_data.txt".format(mode,case)
                # )
                # # 4. save the final trace
                # if replace_with_rowclone:
                #     pre = "rowclone_"
                # else:
                #     pre = "norowclone_"
                # output_file = (
                #     pre + "case{}_alternant_mode.trace"
                #     if alternant
                #     else pre + "case{}_consecutive_mode.trace"
                # )
                outfile = "{}_case{}.trace".format(baseline,case)
                ah.save_to_file(traces, output_dir + outfile)


# split_trace_into3()
# batch_convert_to4line()
create_cache_traces_for_ramulator2()
