export type Item = { id: number; sku: string; name: string; is_meat: boolean };
export type Supplier = { id: number; name: string };
export type Location = { id: number; name: string; kind: string };
export type LossType = { code: string; name: string };

export type ReceivingCreateLotRequest = {
  lot_code: string;
  item_id: number;
  supplier_id: number;
  to_location_id: number;
  quantity_kg: number;
  performed_by: number;
  reason: string;
};

export type ReceivingCreateLotResponse = {
  lot_id: number;
  movement_id: number;
  lot_event_id: number;
};
