import { useOutletContext } from "react-router-dom";
import type { TripDetail } from "../types";

export const useTrip = () => useOutletContext<{ trip?: TripDetail }>().trip;
