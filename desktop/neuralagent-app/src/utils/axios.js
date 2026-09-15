import axios from "axios";
import constants from "./constants";

export default axios.create({
  baseURL: constants.BASE_URL
});

export const API_KEY_HEADER = {
  headers: {
    'Authorization': 'Api-Key ' + constants.API_KEY,
  }
}