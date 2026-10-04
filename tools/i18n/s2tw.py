# Упрощённый → традиционный (тайваньский) на словарях OpenCC: фразы (STPhrases, TWPhrases), затем символы (STCharacters, TWVariants).
import os
D=os.path.join(os.path.dirname(os.path.abspath(__file__)),'OpenCC/data/dictionary')
def load(*names):
    m={}
    for n in names:
        for line in open(os.path.join(D,n),encoding='utf8'):
            p=line.rstrip('\n').split('\t')
            if len(p)>=2 and p[0] not in m: m[p[0]]=p[1].split(' ')[0]
    return m
def conv_with(m,s):
    mx=max(len(k) for k in m); out=[]; i=0
    while i<len(s):
        for L in range(min(mx,len(s)-i),0,-1):
            k=s[i:i+L]
            if k in m: out.append(m[k]); i+=L; break
        else: out.append(s[i]); i+=1
    return ''.join(out)
ST=load('STPhrases.txt','STCharacters.txt'); TW=load('TWPhrases.txt','TWVariants.txt','TWVariantsPhrases.txt')
def s2tw(s): return conv_with(TW,conv_with(ST,s))
if __name__=='__main__':
    print(s2tw('该钱包在选样期内的信号（首次买入）数量 登录 密钥 名单中 跑路占比 数据时间 软件 网络 信息'))
