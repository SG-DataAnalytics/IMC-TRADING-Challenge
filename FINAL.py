from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import pandas as pd

class Product:
    INTARIAN_PEPPER_ROOT = "INTARIAN_PEPPER_ROOT"
    ASH_COATED_OSMIUM = "ASH_COATED_OSMIUM"

class Trader:
    def __init__(self):
        self.LIMIT = {Product.INTARIAN_PEPPER_ROOT: 80,Product.ASH_COATED_OSMIUM: 80 }
        self.params = {Product.ASH_COATED_OSMIUM:{"MIN_SPREAD" : 4, 
                                               "MAX_SPREAD" : 9,
                                               "ORDER_SIZE" : 15,
                                               "JUMP" : 7,
                                               "IMBALANCE_TRESH" : 0.4}}

    def bid():
        return 3001

    def jump_detection(self,traderObject,best_bid,best_ask,params):
        diff_b,diff_a = pd.NA,pd.NA
        if "last_best_bid" in traderObject.keys():
            diff_b = best_bid - traderObject["last_best_bid"]
        if "last_best_ask" in traderObject.keys():
            diff_a = best_ask - traderObject["last_best_ask"]
        trade = None
        if not pd.isna(diff_b):
            if (diff_b >= params["JUMP"] and diff_a > -params["JUMP"]) or (diff_b >= params["JUMP"] and pd.isna(diff_a)):
                trade = "Sell"
        if not pd.isna(diff_a):
            if (diff_a <= -params["JUMP"] and diff_b < params["JUMP"]) or (diff_a <= -params["JUMP"] and pd.isna(diff_b)):
                trade = "Buy"
        return trade

    def update_traderdata(self,traderObject,best_bid,best_ask):
        if not pd.isna(best_bid):
            traderObject["last_best_bid"] = best_bid
        if not pd.isna(best_ask):
            traderObject["last_best_ask"] = best_ask
        return traderObject

    def run(self, state: TradingState):
        result = {}
        traderData = state.traderData
        conversions = 0
        product_list = [Product.INTARIAN_PEPPER_ROOT,Product.ASH_COATED_OSMIUM]
        if Product.INTARIAN_PEPPER_ROOT not in state.order_depths and Product.ASH_COATED_OSMIUM not in state.order_depths:
            return result, conversions, traderData

        if state.traderData is not None and state.traderData != "":
            traderObject = jsonpickle.decode(state.traderData)
        else:
            traderObject = {}
        for p in product_list:
            if p == Product.ASH_COATED_OSMIUM:
                order_depth: OrderDepth = state.order_depths[p]
                orders: List[Order] = []
                param = self.params[p]
                POSITION_LIMIT = self.LIMIT[p]

                # ── 1. Position et Cap ───────────────────────────────────────────────
                position = state.position.get(p, 0)
                buy_cap  = POSITION_LIMIT - position
                sell_cap = POSITION_LIMIT + position

                # ── 2. Analyse de la dynamique du carnet ──────────────────────────────
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid      = (best_bid + best_ask) / 2
                
                # # MODIF : Calcul de l'Imbalance (pression du carnet)
                vol_bid = order_depth.buy_orders[best_bid]
                vol_ask = abs(order_depth.sell_orders[best_ask])
                imbalance = (vol_bid - vol_ask) / (vol_bid + vol_ask)

                # ── 3. CALCUL DU SPREAD DYNAMIQUE ────────────────────────────────────
                # # Si le spread actuel du marché est serré, on réduit notre spread pour 
                # # rester compétitif. Si l'imbalance est forte d'un côté, on décale.
                
                market_spread = best_ask - best_bid
                
                # # Stratégie : On s'adapte à la volatilité locale
                # # Si le spread du marché > 14, on s'élargit à 8 ou 9 pour gagner plus
                # # Si le spread du marché < 14, on descend à 6 ou 5 pour "sniper" le flux
                dynamic_spread = 7 # Base
                trade_bid = True
                trade_ask = True
                if market_spread > 16:
                    dynamic_spread = param["MAX_SPREAD"]
                elif market_spread < 14:
                    dynamic_spread = param["MIN_SPREAD"]

                # ── 4. Jump Detection (Inchangé) ─────────────────────────────────────
                if traderObject != {}:
                    trade = self.jump_detection(traderObject,best_bid,best_ask,param)
                    if trade is not None:
                        if trade == "Sell" and sell_cap > 0:
                            vol = min(vol_bid, sell_cap)
                            orders.append(Order(p, best_bid, -vol))
                            sell_cap -= vol
                            trade_bid = False
                        if trade == "Buy" and buy_cap > 0:
                            vol = min(vol_ask, buy_cap)
                            orders.append(Order(p, best_ask, vol))
                            buy_cap -= vol
                            trade_ask = False

                # ── 5. MAKING ADAPTATIF BASÉ SUR L'ORDER BOOK ────────────────────────
                if not pd.isna(mid):
                    # # MODIF : On ajuste le prix en fonction de l'imbalance
                    # # Si imbalance > IMBALANCE_TRESH (trop d'acheteurs), on monte notre Bid pour être sûr 
                    # # d'être exécuté et on monte notre Ask pour vendre plus cher.
                    skew_imbalance = 0
                    if imbalance > param["IMBALANCE_TRESH"]: skew_imbalance = 1  # Pression haussière
                    if imbalance < -param["IMBALANCE_TRESH"]: skew_imbalance = -1 # Pression baissière

                    our_bid = round(mid - dynamic_spread) + skew_imbalance
                    our_ask = round(mid + dynamic_spread) + skew_imbalance

                    # # Pennying intelligent : on veut être au-dessus du best_bid
                    # # mais on ne veut pas être "trop" généreux
                    our_bid = max(our_bid, best_bid + 1)
                    our_ask = min(our_ask, best_ask - 1)

                    # # Sécurité ultime pour ne pas croiser
                    if our_bid >= best_ask: our_bid = best_ask - 1
                    if our_ask <= best_bid: our_ask = best_bid + 1

                    if buy_cap > 0 and trade_bid:
                        orders.append(Order(p, int(our_bid), min(param["ORDER_SIZE"], buy_cap)))
                    if sell_cap > 0 and trade_ask:
                        orders.append(Order(p, int(our_ask), -min(param["ORDER_SIZE"], sell_cap)))
                traderObject = self.update_traderdata(traderObject,best_bid,best_ask)
                result[p] = orders
            else:
                order_depth = state.order_depths[p]
                position = state.position.get(p, 0)
                orders = []
                # Quantité restante avant d'atteindre la limite
                buy_vol = self.LIMIT[p] - position

                if buy_vol > 0 and order_depth.sell_orders:
                    # On achète au meilleur ask disponible
                    best_ask = min(order_depth.sell_orders.keys())
                    available = -order_depth.sell_orders[best_ask]
                    qty = min(buy_vol, available)
                    orders.append(Order(p, best_ask, qty))
                result[p] = orders

        traderData = jsonpickle.encode(traderObject)

        return result, conversions, traderData