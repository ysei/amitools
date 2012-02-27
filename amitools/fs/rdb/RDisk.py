from ..block.rdb.RDBlock import *
from ..block.rdb.PartitionBlock import *
import amitools.util.ByteSize as ByteSize
import amitools.fs.DosType as DosType
from FileSystem import FileSystem
from Partition import Partition

class RDisk:
  def __init__(self, rawblk):
    self.rawblk = rawblk
    self.valid = False
    self.rdb = None
    self.parts = []
    self.fs = []
    self.hi_rdb_blk = 0

  def open(self):
    # read RDB
    self.rdb = RDBlock(self.rawblk)
    if not self.rdb.read():
      self.valid = False
      return False
      
    # read partitions
    part_blk = self.rdb.part_list
    self.parts = []
    num = 0
    while part_blk != Block.no_blk:
      p = Partition(self.rawblk, part_blk, num, self.rdb.log_drv.cyl_blks, self)
      num += 1
      if not p.read():
        self.valid = False
        return False
      self.parts.append(p)
      # remember highest rdb block
      hi = p.get_highest_blk_num()
      if hi > self.hi_rdb_blk:
        self.hi_rdb_blk = hi
      part_blk = p.get_next_partition_blk()
    
    # read filesystems
    fs_blk = self.rdb.fs_list
    self.fs = []
    num = 0
    while fs_blk != PartitionBlock.no_blk:
      fs = FileSystem(self.rawblk, fs_blk, num)
      num += 1
      if not fs.read():
        self.valid = False
        return False
      self.fs.append(fs)
      # remember highest rdb block
      hi = fs.get_highest_blk_num()
      if hi > self.hi_rdb_blk:
        self.hi_rdb_blk = hi
      fs_blk = fs.get_next_fs_blk()
      
    # TODO: add bad block blocks
    self.valid = True
    return True

  def close(self):
    pass
    
  # ----- query -----
  
  def dump(self, hex_dump=False):
    # rdb
    if self.rdb != None:
      self.rdb.dump()
    # partitions
    for p in self.parts:
      p.dump()
    # fs
    for fs in self.fs:
      fs.dump(hex_dump)
  
  def get_info(self):
    res = []
    # physical disk info
    pd = self.rdb.phy_drv
    total_blks = self.get_total_blocks()
    total_bytes = self.get_total_bytes()
    extra="heads=%d sectors=%d" % (pd.heads, pd.secs)
    res.append("PhysicalDisk:        %8d %8d  %10d  %s  %s" \
      % (0, pd.cyls-1, total_blks, ByteSize.to_byte_size_str(total_bytes), extra))
    # logical disk info
    ld = self.rdb.log_drv
    extra="rdb_blks=[%d:%d,%d(%d)] cyl_blks=%d" % (ld.rdb_blk_lo, ld.rdb_blk_hi, ld.high_rdsk_blk, self.hi_rdb_blk, ld.cyl_blks)
    logic_blks = self.get_logical_blocks()
    logic_bytes = self.get_logical_bytes()
    res.append("LogicalDisk:         %8d %8d  %10d  %s  %s" \
      % (ld.lo_cyl, ld.hi_cyl, logic_blks, ByteSize.to_byte_size_str(logic_bytes), extra))
    # add partitions
    for p in self.parts:
      res.append(p.get_info(logic_blks))
    # add fileystems
    for f in self.fs:
      res.append(f.get_info())
    return res
    
  def get_logical_cylinders(self):
    ld = self.rdb.log_drv
    return ld.hi_cyl - ld.lo_cyl + 1

  def get_logical_blocks(self):
    ld = self.rdb.log_drv
    cyls = ld.hi_cyl - ld.lo_cyl + 1
    return cyls * ld.cyl_blks

  def get_logical_bytes(self, block_bytes=512):
    return self.get_logical_blocks() * block_bytes

  def get_total_blocks(self):
    pd = self.rdb.phy_drv
    return pd.cyls * pd.heads * pd.secs
  
  def get_total_bytes(self, block_bytes=512):
    return self.get_total_blocks() * block_bytes
    
  def get_cylinder_blocks(self):
    ld = self.rdb.log_drv
    return ld.cyl_blks
    
  def get_cylinder_bytes(self, block_bytes=512):
    return self.get_cylinder_blocks() * block_bytes

  def get_num_partitions(self):
    return len(self.parts)
  
  def get_partition(self, num):
    if num < len(self.parts):
      return self.parts[num]
    else:
      return None
  
  def find_partition_by_drive_name(self, name):
    lo_name = name.lower()
    num = 0
    for p in self.parts:
      drv_name = p.get_drive_name().lower()
      if drv_name == lo_name:
        return p
    return None
    
  def find_partition_by_string(self, s):
    p = self.find_partition_by_drive_name(s)
    if p != None:
      return p
    # try partition number
    try:
      num = int(s)
      return self.get_partition(num)
    except ValueError:
      return None
      
  def get_filesystem(self, num):
    if num < len(self.fs):
      return self.fs[num]
    else:
      return None

  # ----- edit -----
  
  def create(self, disk_geo, rdb_cyl=1, hi_rdb_blk=0, disk_names=None, ctrl_names=None):
    cyls = disk_geo.cyls
    heads = disk_geo.heads
    secs = disk_geo.secs
    cyl_blks = heads * secs
    rdb_blk_hi = cyl_blks * rdb_cyl - 1
    
    if disk_names != None:
      disk_vendor = disk_names[0]
      disk_product = disk_names[1]
      disk_revision = disk_names[2]
    else:
      disk_vendor = 'RDBTOOL'
      disk_product = 'IMAGE'
      disk_revision = '2012'
      
    if ctrl_names != None:
      ctrl_vendor = ctrl_names[0]
      ctrl_product = ctrl_names[1]
      ctrl_revision = ctrl_names[2]
    else:
      ctrl_vendor = ''
      ctrl_product = ''
      ctrl_revision = ''
    
    flags = 0x7
    if disk_names != None:
      flags |= 0x10
    if ctrl_names != None:
      flags |= 0x20
    
    # create RDB
    phy_drv = RDBPhysicalDrive(cyls, heads, secs)
    log_drv = RDBLogicalDrive(rdb_blk_hi=rdb_blk_hi, lo_cyl=rdb_cyl, hi_cyl=cyls-1, cyl_blks=cyl_blks, high_rdsk_blk=hi_rdb_blk)
    drv_id = RDBDriveID(disk_vendor, disk_product, disk_revision, ctrl_vendor, ctrl_product, ctrl_revision)
    self.rdb = RDBlock(self.rawblk)
    self.rdb.create(phy_drv, log_drv, drv_id, flags=flags)
    self.rdb.write()
  
  def get_cyl_range(self):
    log_drv = self.rdb.log_drv
    return (log_drv.lo_cyl, log_drv.hi_cyl)
  
  def check_cyl_range(self, lo_cyl, hi_cyl):
    if lo_cyl > hi_cyl:
      return False
    (lo,hi) = self.get_cyl_range()
    if not (lo_cyl >= lo and hi_cyl <= hi):
      return False
    # check partitions
    for p in self.parts:
      (lo,hi) = p.get_cyl_range()
      if not ((hi_cyl < lo) or (lo_cyl > hi)):
        return False
    return True
  
  def get_free_cyl_ranges(self):
    lohi = self.get_cyl_range()
    free = [lohi] 
    for p in self.parts:
      pr = p.get_cyl_range()
      new_free = []
      for r in free:
        # partition completely fills range
        if pr[0] == r[0] and pr[1] == r[1]:
          pass
        # partition starts at range
        elif pr[0] == r[0]:
          n = (pr[1]+1, r[1])
          new_free.append(n)
        # partition ends at range
        elif pr[1] == r[1]:
          n = (r[0], pr[0]-1)
          new_free.append(n)
        # partition inside range
        elif pr[0] > r[0] and pr[1] < r[1]:
          new_free.append((r[0], pr[0]-1))
          new_free.append((pr[1]+1,r[1]))
        else:
          new_free.append(r)
      free = new_free
    return free
  
  def find_free_cyl_range_start(self, num_cyls):
    ranges = self.get_free_cyl_ranges()
    if ranges == None:
      return None
    for r in ranges:
      size = r[1] - r[0] + 1
      if num_cyls <= size:
        return r[0]
    return None
  
  def _has_free_rdb_blocks(self, num):
    return self.hi_rdb_blk + num <= self.rdb.log_drv.rdb_blk_hi
    
  def _alloc_rdb_blocks(self, num):
    blk_num = self.hi_rdb_blk + 1
    self.hi_rdb_blk += num
    return blk_num
    
  def add_partition(self, drv_name, cyl_range, dev_flags=0, flags=0, dos_type=DosType.DOS0, boot_pri=0):
    # cyl range is not free anymore or invalid
    if not self.check_cyl_range(*cyl_range):
      return False
    # no space left for partition block
    if not self._has_free_rdb_blocks(1):
      return False
    # crete a new parttion block
    blk_num = self._alloc_rdb_blocks(1)
    pb = PartitionBlock(self.rawblk, blk_num)
    heads = self.rdb.phy_drv.heads
    blk_per_trk = self.rdb.phy_drv.secs
    dos_env = PartitionDosEnv(low_cyl=cyl_range[0], high_cyl=cyl_range[1], surfaces=heads, \
                              blk_per_trk=blk_per_trk, dos_type=dos_type, boot_pri=boot_pri)
    pb.create(drv_name, dos_env, flags=flags)
    pb.write()
    # link block
    if len(self.parts) == 0:
      # write into RDB
      self.rdb.part_list = blk_num
      self.rdb.write()
    else:
      # write into last partition block
      last_pb = self.parts[-1]
      last_pb.part_blk.next = blk_num
      last_pb.write()
    # create partition object and add to partition list
    p = Partition(self.rawblk, blk_num, len(self.parts), blk_per_trk, self)
    p.read()
    self.parts.append(p)
    return True
    
    
    