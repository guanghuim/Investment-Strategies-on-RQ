import pandas as pd
import numpy as np
import time
import math
import itertools

# 数据准备

def init_variables (context):
    context.s1 = '000001.XSHG'
    context.init=0
    context.max_num_stocks = 50
    context.days = 0
    context.barcount = 0
    context.month_days = 22
    context.relative_strength_6m = {}
    return


'''选择股票池'''

def choose_target(context, bar_dict):
    # 根据动量选择合适的股票
    fundamental_df = get_fundamentals(
        query(
             
            fundamentals.cash_flow_statement.cash_flow_from_financing_activities,
            fundamentals.eod_derivative_indicator.market_cap,
            fundamentals.cash_flow_statement.cash_from_operating_activities,
            fundamentals.financial_indicator.invested_capital,
            fundamentals.financial_indicator.return_on_invested_capital,
            fundamentals.balance_sheet.cash,
            fundamentals.balance_sheet.cash_equivalent,
            fundamentals.cash_flow_statement.cash_from_operating_activities,
            fundamentals.income_statement.net_profit,
            fundamentals.eod_derivative_indicator.market_cap,
            fundamentals.financial_indicator.fcff
        )
        
        .filter(fundamentals.eod_derivative_indicator.market_cap > 0)
        .filter(fundamentals.cash_flow_statement.cash_from_operating_activities > fundamentals.income_statement.net_profit)
        .filter((fundamentals.eod_derivative_indicator.market_cap / fundamentals.financial_indicator.fcff) < 15)
        .filter(fundamentals.financial_indicator.invested_capital > 0)
        .filter((fundamentals.cash_flow_statement.cash_flow_from_financing_activities / fundamentals.eod_derivative_indicator.market_cap) < 0.05) #此项大幅提升了夏普比率
        .filter(fundamentals.financial_indicator.return_on_invested_capital > 0.20)      
        .limit(context.max_num_stocks)
    )

    context.stocks = [stock for stock in fundamental_df]
    context.fundamental_df = fundamental_df
    return context.stocks

'''入场策略'''
#2.1 大盘环境问题
    #可增加外部数据

#2.2 个股选择问题，最后还要过滤非跌停、上市天数、非停牌的标的（st未过滤）
def for_buy(context, bar_dict):
    to_buy= [stock for stock in context.stocks
                      if stock in bar_dict and context.relative_strength_6m[stock] > -0.6745 and context.relative_strength_6m[stock] < 9999]

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
# 将不在股票池中的已购股票出仓
def for_sell(context, bar_dict):
    to_sell = []
    for stock in context.portfolio.positions:
        if stock not in context.fundamental_df:
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

# 计算过去六个月的价格变化率
def compute_relative_strength(context):
    prices = history (150, '1d', 'close')
    pct_change = (prices.ix[149] - prices.ix[19]) / prices.ix[19]
    print(prices.ix[19])
    print(pct_change)
    priceofbase = history (150, '1d', 'close')[context.s1]
    pct_changeforbase = (priceofbase.ix[149] - priceofbase.ix[19]) / priceofbase.ix[19]
    pct_change = pct_change - pct_changeforbase
    if pct_changeforbase != 0:
        pct_change = pct_change / abs(pct_changeforbase)
    context.relative_strength_6m = pct_change

# 选择调仓时间
def month_passed(context): 
    return context.days % context.month_days == 0
'''--------------操作部分----------------'''

def init(context):
    init_variables(context)


# before_trading此函数会在每天交易开始前被调用，当天只会被调用一次
def before_trading(context, bar_dict):
    context.days += 1
    context.barcount=0
    if not month_passed(context):
        return

    choose_target(context, bar_dict)#选择小盘的股票池
    update_universe(context.stocks)
    context.init = 1
    pass


# 你选择的证券的数据更新将会触发此段逻辑，例如日或分钟历史数据切片或者是实时数据切片更新
def handle_bar(context, bar_dict):
    context.barcount += 1
    
    alert_rish(context,bar_dict)
    
    #模拟交易第一次开始，如果是交易时间可能运行不了before_trading,所以这里做了个参数来控制这种出错的特例
    if context.init == 0:
        context.days += 1
        context.barcount=0
        if not month_passed(context):
            return

        choose_target(context, bar_dict)#选择小盘的股票池
        update_universe(context.stocks)
        context.init = 1
    else:
        pass
    
    compute_relative_strength(context)
        
    to_sell = for_sell(context, bar_dict)
    if to_sell:
        print(to_sell)
        for oid in get_open_orders():#将卖出列表中尚未完成的买入订单撤单
            cancel_order(oid)
        for stock in to_sell:
            order_target_value(stock, 0, style=LimitOrder(bar_dict[stock].last*0.995))#实际算上手续费，卖出价格低于市场价格

    to_buy = for_buy(context, bar_dict)
    if to_buy:
        print (to_buy)
    hnum = len(list(set(to_buy).union(set(context.portfolio.positions.keys()))))
    for stock in to_buy:
        if hnum <10:
            print ('buy', stock, bar_dict[stock].high * 1.005)
            order_target_percent(stock, 0.99/10, style=LimitOrder(bar_dict[stock].high * 1.005))#不足十只股票时剩余资金投资其他产品。由于有买入成本，实际买入价格高于市场价格
        else:
            order_target_percent(stock, 0.99/hnum, style=LimitOrder(bar_dict[stock].high * 1.005))

    for_balance(context, bar_dict)
    for_cash(context, bar_dict)