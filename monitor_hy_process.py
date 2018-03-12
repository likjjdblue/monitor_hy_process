#-*- encoding:utf-8 -*-
#!/usr/bin/env python

import subprocess
from time  import sleep
from datetime import datetime
from collections import deque
import re
from os import path,makedirs,kill
from math import ceil
import threading
import signal

class monitorHYProcess:
   def __init__(self):
      self.GlobalSampleInterval=1     ###采集系统资源使用数据时间间隔, 单位：秒  ####
      self.GlobalSamplesListLength=3   ###采集系统资源样本list最大长度(采用FIFO 循环队列的方式)   ###
      self.AvailableRAMThreshold=500   ###操作系统可用内存大小阀值，单位:兆
      self.AvailableCPUPercentThreshold=30       ###操作系统可用CPU 百分比阀值   ###
      self.CPUDeltaThreshold=0       ### 操作系统CPU过快消耗百分比阀值  ###
      self.RAMDeltaThreshold=5       ### 操作系统内存过快消耗阀值,单位：兆
      self.GlobalFileObj=open('running.log',mode='ab',buffering=0)  ###全局日志文件

      self.ProcessDeltaCPUThreshold=10   ### 单个进程CPU 消耗速度阀值(单位：CPU 百分比)   ###
      self.ProcessDeltaRAMThreshold=50   #### 单个进程RAM 消耗速度阀值(单位：兆)


      self.FlagOfQuit=False         ### 子线程 是否强制退出 标志位   ##
      self.ResourceState='good'
      self.Dict4Threadname={}
      self.TargetJAVAInstalledPathList=['/TRS/HyCloud/IIP',
                                      '/TRS/HyCloud/IGI',
                                      '/TRS/HyCloud/IPM',
                                      '/TRS/HyCloud/IRT',
                                      ]    ###需要监控的 JAVA 程序的路径    ####
            
      CurrentTimeString=datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
      ####  检测 vmstat jstack 是否正常   ####
      if subprocess.call('which vmstat',shell=True,stdout=subprocess.PIPE):
         self.GlobalFileObj.write(CurrentTimeString+' 未检测到vmstat工具，程序退出\n')
         self.GlobalFileObj.close()
         raise Exception('未检测到vmstat工具，程序退出')
      if subprocess.call('which jstack',shell=True,stdout=subprocess.PIPE):
         self.GlobalFileObj.write(CurrentTimeString+' 未检测到jstack工具，程序退出\n')
         self.GlobalFileObj.close()
         raise Exception('未检测到jstack工具，程序退出')
      self.GlobalFileObj.write(CurrentTimeString+' jstack 和 vmstat 工具 检测正常\n')


      TmpCPUInfo=subprocess.Popen('lscpu',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
      TmpRAMInfo=subprocess.Popen('cat /proc/meminfo',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
      self.GlobalFileObj.write(TmpCPUInfo+'\n')
      self.GlobalFileObj.write(TmpRAMInfo+'\n')
      
      self.__extractTotalRAM()

 
   def __extractTotalRAM(self):
      TmpTotalRAM=subprocess.Popen("free -m|grep 'Mem:'|awk '{print $2}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
      self.TotalRAMSize=int(TmpTotalRAM.strip())
      print ('内存大小：'+str(self.TotalRAMSize))

   def __generateJVMSnapshot(self,name,pid,timestring,tmpobj):
       if not path.isdir(path.join('logs',name,'jvm')):
          makedirs(path.join('logs',name,'jvm'))

       TmpJVMSnapshot=tmpobj.communicate()[0]
       with open(path.join('logs',name,'jvm',name+'_'+str(pid)+'_'+timestring+'_'+'jstack.log'),mode='wb') as f:
           f.write(TmpJVMSnapshot)

   def monitorSystemResourceUsage(self):
       ###监控操作系统CPU MEMORY  使用情况 ####
       QueueObj4CPU=deque(maxlen=self.GlobalSamplesListLength) 
       QueueObj4RAM=deque(maxlen=self.GlobalSamplesListLength)
       TmpPreviousAvailableCPU=None
       TmpPreviousAvailableRAM=None

       while not self.FlagOfQuit:
          CurrentTimeString=datetime.now().strftime('%Y-%m-%d_%H:%M:%S')

          ### 提取当前内存使用情况 ###
          TmpRAMResult=subprocess.Popen("free -m",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
          TmpAvailableRAM=re.search(r'(^Mem:.*?\n)',TmpRAMResult,flags=re.MULTILINE).group(1).strip().split()[6]
          TmpAvailableRAM=int(TmpAvailableRAM)

          ####提取当前CPU 使用情况  ###
          TmpCPUResult=subprocess.Popen("top -bn 1 | grep '^%Cpu'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
          TmpAvailableCPU=re.search('ni,(.*?)id',TmpCPUResult,flags=re.MULTILINE).group(1).strip()
          TmpAvailableCPU=int(float(TmpAvailableCPU))

          if (TmpAvailableRAM<=self.AvailableRAMThreshold) or (TmpAvailableCPU<=self.AvailableCPUPercentThreshold):    ### CPU 或则 内存过载    ##
             self.ResourceState='bad'
             self.GlobalFileObj.write('*'*20+CurrentTimeString+'*'*20+'\n')
             self.GlobalFileObj.write('CPU使用过高，或内存不足\n')
             self.GlobalFileObj.write(TmpRAMResult+'\n')
             self.GlobalFileObj.write(TmpCPUResult+'\n')
             self.GlobalFileObj.write('*'*30+'END'+'*'*30+'\n\n')
             
             if not path.isdir(path.join('logs','cpu')):
                makedirs(path.join('logs','cpu'))
             if not path.isdir(path.join('logs','ram')):
                makedirs(path.join('logs','ram'))

             ###  生成快照  order by cpu  ####
             TmpSnapshot=subprocess.Popen('ps axu k -pcpu',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
             with open(path.join('logs','cpu','cpu_'+CurrentTimeString+'.log'),mode='wb') as f:
                 f.write(TmpSnapshot)

             ### 生成快照 order by ram  ###
             TmpSnapshot=subprocess.Popen('ps axu k -vsz',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
             with open(path.join('logs','ram','ram_'+CurrentTimeString+'.log'),mode='wb') as f:
                 f.write(TmpSnapshot)
             sleep(self.GlobalSampleInterval)
             continue
          else:
              if not path.isdir(path.join('logs','cpu')):
                 makedirs(path.join('logs','cpu'))
              if not path.isdir(path.join('logs','ram')):
                 makedirs(path.join('logs','ram'))
              TmpFlagOK=True    ## 当内存或CPU 消耗速度没有超过阀值，就不会被设置成False;该标志位间接影响self.ResourceState###

              if len(QueueObj4CPU)<1:
                 TmpPreviousAvailableCPU=TmpAvailableCPU
                 TmpPreviousAvailableRAM=TmpAvailableRAM
                 QueueObj4CPU.append(0) 
                 QueueObj4RAM.append(0)
                 continue
              elif len(QueueObj4CPU)>=1:
                 TmpDeltaCPU=TmpAvailableCPU-TmpPreviousAvailableCPU
                 TmpDeltaRAM=TmpAvailableRAM-TmpPreviousAvailableRAM 
                 QueueObj4CPU.append(TmpDeltaCPU)
                 QueueObj4RAM.append(TmpDeltaRAM)
                 TmpPreviousAvailableCPU=TmpAvailableCPU
                 TmpPreviousAvailableRAM=TmpAvailableRAM

                 TmpAverageCPUDelta=int(ceil(float(sum(QueueObj4CPU))/len(QueueObj4CPU)))    #### CPU近期平均消耗速度  ##
                 TmpAverageRAMDelta=int(ceil(float(sum(QueueObj4RAM))/len(QueueObj4RAM)))    ###内存近期平均消耗速度   ###

                 if TmpAverageCPUDelta<0 and  abs(TmpAverageCPUDelta)>=self.CPUDeltaThreshold:
                    TmpFlagOK=False
                    self.ResourceState='bad'

                    self.GlobalFileObj.write('*'*20+CurrentTimeString+'*'*20+'\n')
                    self.GlobalFileObj.write('CPU过快消耗\n'+'消耗速度'+str(TmpAverageCPUDelta)+'\n')
                    self.GlobalFileObj.write(str(QueueObj4CPU)+'\n')
                    self.GlobalFileObj.write(TmpCPUResult+'\n')
                    self.GlobalFileObj.write('*'*30+'END'+'*'*30+'\n\n')

                    TmpSnapshot=subprocess.Popen('top -b -n 1 -o %CPU',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
                    with open(path.join('logs','cpu','cpu_'+CurrentTimeString+'.log'),mode='wb') as f:
                        f.write(TmpSnapshot)

                 if TmpAverageRAMDelta<0 and abs(TmpAverageRAMDelta)>=self.RAMDeltaThreshold:
                    TmpFlagOK=False
                    self.ResourceState='bad'

                    self.GlobalFileObj.write('*'*20+CurrentTimeString+'*'*20+'\n')
                    self.GlobalFileObj.write('内存消耗过快\n'+'消耗速度'+str(TmpAverageRAMDelta)+'\n')
                    self.GlobalFileObj.write(str(QueueObj4RAM))
                    self.GlobalFileObj.write(TmpRAMResult+'\n')
                    self.GlobalFileObj.write('*'*30+'END'+'*'*30+'\n\n')
                    TmpSnapshot=subprocess.Popen('top -b -n 1 -o %MEM',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
                    with open(path.join('logs','ram','ram_'+CurrentTimeString+'.log'),mode='wb') as f:
                        f.write(TmpSnapshot)
                 if TmpFlagOK==True:
                    self.ResourceState='good'
                                     
          sleep(self.GlobalSampleInterval)
      
   def monitorProcess(self,name,pid,cpudelta,ramdelta):
       name=name.strip()
       pid=pid.strip()
       self.Dict4Threadname.setdefault(name,pid)
       QueueObj4CPU=deque(maxlen=self.GlobalSamplesListLength)
       QueueObj4RAM=deque(maxlen=self.GlobalSamplesListLength)
       TmpPreviousUsedCPU=None
       TmpPreviousUsedRAM=None

       while not self.FlagOfQuit:
          CurrentTimeString=datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
          if not path.isdir(path.join('logs',name,'top')):
             makedirs(path.join('logs',name,'top'))
          if not path.isdir(path.join('logs',name,'ps')):
             makedirs(path.join('logs',name,'ps'))
          if not path.isdir(path.join('logs',name,'jvm')):
             makedirs(path.join('logs',name,'jvm'))

          try:
             kill(int(pid.strip()),0)
          except:
             self.GlobalFileObj.write(CurrentTimeString+' 进程名称：'+str(name)+' PID:'+str(pid)+'不存在或程序已经退出.子线程退出\n')
             break
          
          TmpSnapshotA,TmpErrorA=subprocess.Popen('top -p %s -b -n 1 -H'%(pid.strip(),),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()
          TmpCmd='ps -p %s ww -o user,pid,ppid,lwp,nlwp,pcpu,pmem,vsz,rss,size,stat,stime,etime,cputime,args,cmd,comm'%(pid.strip(),)
          TmpSnapshotB,TmpErrorB=subprocess.Popen(TmpCmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()

          ReObj=re.search(r'^(\s*\d+.*?)\n',TmpSnapshotA,flags=re.MULTILINE)
          if not ReObj:
             self.GlobalFileObj.write(CurrentTimeString+' 进程名称：'+str(name)+' PID:'+str(pid)+'不存在或程序已经退出.子线程退出\n')
             break

          TmpResult=ReObj.group(1).strip().split()
          TmpCurrentUsedCPU,TmpCurrentUsedRAM=float(TmpResult[8].strip()),float(TmpResult[9].strip())
                    
          if len(QueueObj4CPU)<1:
             QueueObj4CPU.append(0)
             QueueObj4RAM.append(0)
             TmpPreviousUsedCPU=TmpCurrentUsedCPU
             TmpPreviousUsedRAM=TmpCurrentUsedRAM
             continue
          else:
             TmpUsedDeltaCPU=TmpCurrentUsedCPU-TmpPreviousUsedCPU
             TmpUsedDeltaRAM=(TmpCurrentUsedRAM-TmpPreviousUsedRAM)*self.TotalRAMSize*0.01
             QueueObj4CPU.append(TmpUsedDeltaCPU)
             QueueObj4RAM.append(TmpUsedDeltaRAM)

             TmpPreviousUsedCPU=TmpCurrentUsedCPU
             TmpPreviousUsedRAM=TmpCurrentUsedRAM
             TmpAverageCPUDelta=ceil(float(sum(QueueObj4CPU))/len(QueueObj4CPU))
             TmpAverageRAMDelta=int(ceil(float(sum(QueueObj4RAM))/len(QueueObj4RAM)))

          if self.ResourceState=='bad':
             self.GlobalFileObj.write(CurrentTimeString+':线程:'+name+' PID:'+str(pid)+'生成快照\n\n')
             with open(path.join('logs',name,'top',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'top.log'),mode='wb') as f:
                f.write(TmpSnapshotA) 

             with open(path.join('logs',name,'ps',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'ps.log'),mode='wb') as f:
                f.write(TmpSnapshotB)

             TmpObj=subprocess.Popen('jstack -l %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
             ThreadObj=threading.Thread(target=self.__generateJVMSnapshot,args=[name,pid,CurrentTimeString,TmpObj])
             ThreadObj.start()
             ThreadObj.join(8.0)
             if ThreadObj.is_alive():
                try:
                    TmpObj.terminate()
                except:
                    pass
                self.GlobalFileObj.write(name+'PID:'+str(pid)+' jstack 无响应，重新获取JVM 信息\n')
                TmpSnapshotC=subprocess.Popen('jstack -F %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
                with open(path.join('logs',name,'jvm',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'jstack.log'),mode='wb') as f:
                    f.write(TmpSnapshotC)
          else:
             if TmpAverageCPUDelta>cpudelta:
                self.GlobalFileObj.write('*'*30+' '+CurrentTimeString+' '+'*'*30+'\n')
                self.GlobalFileObj.write(CurrentTimeString+' : '+name+' PID: '+str(pid)+' 消耗CPU过快\n')
                self.GlobalFileObj.write('消耗速度：'+str(TmpAverageCPUDelta)+'\n')
                self.GlobalFileObj.write(str(QueueObj4CPU)+'\n')
                self.GlobalFileObj.write('*'*30+' END '+'*'*30+'\n\n')
                
                self.GlobalFileObj.write(CurrentTimeString+':线程:'+name+' PID:'+str(pid)+'生成快照\n')
                with open(path.join('logs',name,'top',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'top.log'),mode='wb') as f:
                     f.write(TmpSnapshotA)
                
                with open(path.join('logs',name,'ps',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'ps.log'),mode='wb') as f:
                     f.write(TmpSnapshotB)

                TmpObj=subprocess.Popen('jstack -l %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                ThreadObj=threading.Thread(target=self.__generateJVMSnapshot,args=[name,pid,CurrentTimeString,TmpObj])
                ThreadObj.start()
                ThreadObj.join(8.0)
                if ThreadObj.is_alive():
                    TmpObj.terminate()
                    self.GlobalFileObj.write(CurrentTimeString+' : '+name+'PID:'+str(pid)+' jstack 无响应，重新获取JVM 信息\n')
                    TmpSnapshotC=subprocess.Popen('jstack -F %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
                    with open(path.join('logs',name,'jvm',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'jstack.log'),mode='wb') as f:
                         f.write(TmpSnapshotC)
             if TmpAverageRAMDelta>ramdelta:
                self.GlobalFileObj.write('*'*30+' '+CurrentTimeString+' '+'*'*30+'\n')
                self.GlobalFileObj.write(CurrentTimeString+' : '+name+' PID: '+str(pid)+' 消耗内存过快\n')
                self.GlobalFileObj.write('消耗速度：'+str(TmpAverageRAMDelta)+'\n')
                self.GlobalFileObj.write(str(QueueObj4RAM)+'\n')
                self.GlobalFileObj.write('*'*30+' END '+'*'*30+'\n\n')


                self.GlobalFileObj.write(CurrentTimeString+':线程:'+name+' PID:'+str(pid)+'生成快照\n')
                with open(path.join('logs',name,'top',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'cpu.log'),mode='wb') as f:
                     f.write(TmpSnapshotA)
                
                with open(path.join('logs',name,'ps',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'ps.log'),mode='wb') as f:
                     f.write(TmpSnapshotB)

                TmpObj=subprocess.Popen('jstack -l %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                ThreadObj=threading.Thread(target=self.__generateJVMSnapshot,args=[name,pid,CurrentTimeString,TmpObj])
                ThreadObj.start()
                ThreadObj.join(3.0)
                if ThreadObj.is_alive():
                    TmpObj.terminate()
                    self.GlobalFileObj.write(name+'PID:'+str(pid)+' jstack 无响应，重新获取JVM 信息\n')
                    TmpSnapshotC=subprocess.Popen('jstack -F %s'%(pid,),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
                    with open(path.join('logs',name,'jvm',name+'_'+str(pid)+'_'+CurrentTimeString+'_'+'jstack.log'),mode='wb') as f:
                         f.write(TmpSnapshotC)
          sleep(self.GlobalSampleInterval)

       self.Dict4Threadname.pop(name)
       CurrentTimeString=datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
       self.GlobalFileObj.write(CurrentTimeString+' 线程退出:'+name+' PID:'+str(pid)+'\n')
       exit(0)


   def discoverySerivces(self):
       while not self.FlagOfQuit:
           CurrentTimeString=datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
           TmpResult=subprocess.Popen("jps |grep -v 'Jps'|awk '{print $1}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
           TmpPIDList=re.findall(r'\d+',TmpResult)
           for TmpPID in TmpPIDList:
               try:
                   with open(r'/proc/%s/cmdline'%(TmpPID,),mode='r') as f:
                       TmpFileContent=f.read()
               except:
                   print ('异常发生，忽略')
                   continue
               for TmpPathItem in self.TargetJAVAInstalledPathList:
                   if TmpPathItem in TmpFileContent:
                       TmpServiceName=path.basename(path.normpath(TmpPathItem+'/'))
                       if (TmpServiceName in self.Dict4Threadname) and (TmpPID!=self.Dict4Threadname[TmpServiceName]):
                           self.GlobalFileObj.write(CurrentTimeString+' 检测到多个相同进程，进程名称：'+\
                                        TmpServiceName+' '+str(self.Dict4Threadname[TmpServiceName])+\
                                                   ' '+TmpPID+'\n')
                           print (CurrentTimeString+' 相同的进程命令参数：'+TmpFileContent+'\n')
                       elif TmpServiceName not in self.Dict4Threadname:
                           self.GlobalFileObj.write(CurrentTimeString+' 检测到新的JAVA进程,PID:'+TmpPID+' 名称：'+TmpServiceName+'\n')
                           threading.Thread(target=self.monitorProcess,args=[TmpServiceName,TmpPID,
                                                                            self.ProcessDeltaCPUThreshold,
                                                                            self.ProcessDeltaRAMThreshold]).start()
           sleep(1)
       self.GlobalFileObj.write('discovery service 线程退出\n')
       exit(0)



   def mainStart(self):
       def __signalHandle(signal,frame):
           print ('捕获到信号量： '+str(signal))
           self.FlagOfQuit=True
           while True:
               RunningThreadNum=threading.activeCount()
               if RunningThreadNum>1:
                   print ('等待子线程退出：'+str(RunningThreadNum))
                   sleep(0.5)
               elif RunningThreadNum==1:
                   print ('主进程退出')
                   exit(0)

       signal.signal(signal.SIGTSTP,__signalHandle)
       signal.signal(signal.SIGQUIT,__signalHandle)
       signal.signal(signal.SIGINT,__signalHandle)
       signal.signal(signal.SIGTERM,__signalHandle)

       threading.Thread(target=self.monitorSystemResourceUsage).start()
       threading.Thread(target=self.discoverySerivces).start()

       while True:
           sleep(3)


                                  
        
'''try:
  TmpObj=monitorHYProcess()
  TmpObj.startMain()
except:
  print ('主进程即将退出...')
  TmpObj.FlagOfQuit=True
 
  while True:
      ThreadNumber=threading.active_count()
      print ('线程总数:'+str(ThreadNumber))
      sleep (1)'''
    




#TmpObj.monitorSystemResourceUsage()
#TmpObj.monitorProcess('iip','1')

TmpObj=monitorHYProcess()
TmpObj.mainStart()


