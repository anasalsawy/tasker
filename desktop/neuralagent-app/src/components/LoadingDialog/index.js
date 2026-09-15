import React from 'react';
import { LoadingDialogContainer, LoadingDialogOverlay } from './LoadingDialogElements';
import ClipLoader from "react-spinners/ClipLoader";

function LoadingDialog() {
  return (
    <>
      <LoadingDialogOverlay />
      <LoadingDialogContainer>
        <ClipLoader
          color="var(--secondary-color)"
          size={100}
        />
      </LoadingDialogContainer>
    </>
  );
}

export default LoadingDialog;
