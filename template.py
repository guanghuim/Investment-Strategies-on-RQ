import pandas as pd
import numpy as np
import time
import math
import itertools

# 数据准备

def init_variables (context):
    context.init = 0 
    context.days = 0
    context.barcount = 0
    context.choosenum = 300
    context.obv = 50
    context.tj1 = 5 # 5日均线
    context.tj2 = 10 # 10日均线
    context.tj3 = 20 # 20日均线
    context.his = pd.DataFrame()
    return


'''选择股票池'''

def choose_target(context, bar_dict):
    # 最小市值的100只标的
    df = get_fundamentals(
        query(fundamentals.eod_derivative_indicator.market_cap)
        .order_by(fundamentals.eod_derivative_indicator.market_cap.asc())
        .limit(context.choosenum)
    )
    context.stocks = [stock for stock in df][:100]
    return context.stocks

'''入场策略'''
#2.1 大盘环境问题
    #可增加外部数据

#2.2 个股选择问题，最后还要过滤非跌停、上市天数、非停牌的标的（st未过滤）
def for_buy(context, bar_dict, his):
    #2.2.1 备选中标的站上5日线
    def tj1(context, bar_dict, his):
#       ma_n = pd.rolling_mean(his, context.tj1)
        ma_n = his.rolling(context.tj1).mean()
        temp = his - ma_n
        temp_s = list(temp[temp>0].iloc[-1,:].dropna().index)
        return temp_s
    #2.2.2 备选中标的站上10日线
    def tj2(context, bar_dict, his):
        ma_n = his.rolling(context.tj2).mean()
        temp = his - ma_n
        temp_s = list(temp[temp>0].iloc[-1,:].dropna().index)
        return temp_s
    
    #2.2.2 所谓金叉，今天短均线大于长均线，上一个bar反之
    def tj3(context, bar_dict, his):
        mas = his.rolling(context.tj1).mean()
        mal = his.rolling(context.tj2).mean()
        temp = mas - mal
        temp_jc = list(temp[temp>0].iloc[-1,:].dropna().index)
        temp_r = list(temp[temp>0].iloc[-2,:].dropna().index)
        temp = []
        for stock in temp_jc:
            if stock not in temp_r:
                temp.append(stock)
        return temp
    
    #整合各个子条件的交集
    
    l1 = tj1(context, bar_dict, his)
    l2 = tj2(context, bar_dict, his)
    l3 = tj3(context, bar_dict, his)
    l_tar = jj_list([l1,l2,l3])
    to_buy = []
    #过滤上市时间、是否涨停、是否停牌等条件
    if l_tar:
        for stock in l_tar:
            con1 = ipo_days(stock,context.now)>60
            con2 = zdt_trade(stock,context,bar_dict)
            con3 = bar_dict[stock].is_trading
            if con1 & con2 & con3:
                to_buy.append(stock)
    return to_buy


'''持仓组合的再平衡'''
# 平均市值做微调
def for_balance(context, bar_dict):
    #mvalues = context.portfolio.market_value
    #avalues = context.portfolio.portfolio_value
    #per = mvalues / avalues
    hlist = []
    for stock in context.portfolio.positions:
        hlist.append([stock,bar_dict[stock].last * context.portfolio.positions[stock].quantity])
    
    if hlist:
        hlist = sorted(hlist,key=lambda x:x[1], reverse=True)
        temp = 0
        for li in hlist:
            temp += li[1]
        for li in hlist:
            if bar_dict[li[0]].is_trading:
                order_target_value(li[0], temp/len(hlist))#对于仓内的股票取相同的权重
    return

'''出场策略'''
# 小于20日均线，并且可交易，没跌停
def for_sell(context, bar_dict):
    to_sell = []
    for stock in context.portfolio.positions:
        con1 = bar_dict[stock].last < 0.99 * bar_dict[stock].mavg(20, frequency='day')
        con2 = bar_dict[stock].is_trading
        con3 = zdt_trade(stock,context,bar_dict)
        if con1 & con2 & con3:
            to_sell.append(stock)
    return to_sell

'''闲置资金效率最大化'''
def for_cash(context, bar_dict):
    cash = context.portfolio.cash
    #order_target_value('511880.XSHG',cash) 注释掉因为滑点太大，可以买一个货基，或者逆回购
    return 

'''风险控制'''
def alert_rish(context,bar_dict):
    #这里如果给出策略，要强制执行，注意在handle优先级高于所有
    pass

'''备用组件'''

# 计算n日概率随机交易的概率收益率
def rts_sj(df,n,m): 
    dfp_pct = df.pct_change()
    def the_list(df,n,m):
        temp = []
        for i in range(n,n+m):
            temp.append(df.iloc[-i,:] + 1)
        return temp
    def from_list(self,num):
        result = []
        for i in range(1,num+1):
            result.extend(list(itertools.combinations(self,i)))
        return result
    def rts_n(tu):
        sum0 = []
        for i in tu:
            temp = 1
            for z in i:
                temp = temp * z
            temp = temp**(1/len(i))
            sum0.append(temp)
        sum1 = 0
        for i in sum0:
            sum1 = sum1 + i - 1
        return sum1/len(sum0)
    return rts_n(from_list(the_list(dfp_pct,n,m),m)) 

# 多list获得并集
def jj_list(tar_list):
    temp = tar_list[0]
    for i in tar_list:
        temp = list(set(temp).intersection(set(i)))
    return temp

# 标的上市时间距离参照时间的自然日数量
def ipo_days(stock, today):
    ssrq = instruments(stock).listed_date.replace(tzinfo=None)
    today = today.replace(tzinfo=None)
    return (today - ssrq).days

# 判断当前标在可交易区间内（非涨跌停）
def zdt_trade(stock, context, bar_dict):
    yesterday = history(2,'1d', 'close')[stock].values[-1]
    zt = round(1.10 * yesterday,2)
    dt = round(0.99 * yesterday,2)
    return dt < bar_dict[stock].last < zt
    



'''--------------操作部分----------------'''

def init(context):
    init_variables(context)


# before_trading此函数会在每天交易开始前被调用，当天只会被调用一次
def before_trading(context, bar_dict):
    choose_target(context, bar_dict)#选择小盘的股票池
    update_universe(context.stocks)
    context.his = history(context.obv,'1d','close')
    context.barcount = 0
    context.init = 1
    pass


# 你选择的证券的数据更新将会触发此段逻辑，例如日或分钟历史数据切片或者是实时数据切片更新
def handle_bar(context, bar_dict):
    context.barcount += 1
    
    alert_rish(context,bar_dict)
    
    #模拟交易第一次开始，如果是交易时间可能运行不了before_trading,所以这里做了个参数来控制这种出错的特例
    if context.init == 0:
        choose_target(context, bar_dict)
        update_universe(context.stocks)
        context.his = history(obv,'1d','close')
        context.barcount = 0
        context.init = 1
    else:
        pass
    
    if context.barcount % 15 == 0:#每15天进行卖出操作
        to_sell = for_sell(context, bar_dict)
        if to_sell:
            print(to_sell)
            for oid in get_open_orders():#将卖出列表中尚未完成的买入订单撤单
                cancel_order(oid)
            for stock in to_sell:
                order_target_value(stock, 0, style=LimitOrder(bar_dict[stock].last*0.995))#实际算上手续费，卖出价格低于市场价格
    
    if context.barcount == 230:
        his = history(2,'1m','close')
        his = context.his.append(his.iloc[-1,:],ignore_index=True)
        to_buy = for_buy(context, bar_dict, his)
        if to_buy:
            print (to_buy)
        hnum = len(list(set(to_buy).union(set(context.portfolio.positions.keys()))))
        for stock in to_buy:
            if hnum <10:
                print ('buy', stock, bar_dict[stock].high * 1.005)
                order_target_percent(stock, 0.99/10, style=LimitOrder(bar_dict[stock].high * 1.005))#不足十只股票时剩余资金投资其他产品。由于有买入成本，实际买入价格高于市场价格
            else:
                order_target_percent(stock, 0.99/hnum, style=LimitOrder(bar_dict[stock].high * 1.005))
    
    if context.barcount == 236: 
        his = history(2,'1m','close')
        his = context.his.append(his.iloc[-1,:],ignore_index=True)
        for_balance(context, bar_dict)
        for_cash(context, bar_dict)
        
        
        